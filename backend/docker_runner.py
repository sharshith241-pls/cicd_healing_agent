"""
Docker Runner
-------------
Runs a target repository inside an isolated Docker container.

Flow:
    Repository
        ↓
    Docker container
        ↓
    Install dependencies
        ↓
    Run tests
        ↓
    Capture logs
        ↓
    Return structured result
"""

from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def detect_project_type(repo_path: str | Path) -> str:
    """Detect one supported test runtime from root-level project manifests."""

    repository = Path(repo_path)
    if not repository.is_dir():
        raise ValueError(f"Repository does not exist: {repository}")
    if (repository / "pom.xml").is_file() or (
        (repository / "build.gradle").is_file()
        or (repository / "build.gradle.kts").is_file()
    ):
        return "java"
    if (repository / "go.mod").is_file():
        return "go"
    package_json = repository / "package.json"
    if package_json.is_file():
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read package.json: {exc}") from exc
        if not isinstance(package_data, dict) or not (
            package_data.get("scripts", {}).get("test")
            if isinstance(package_data.get("scripts", {}), dict)
            else None
        ):
            raise ValueError("package.json must define scripts.test.")
        return "node"
    if any(
        (repository / marker).is_file()
        for marker in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile")
    ) or any(repository.glob("*.py")):
        return "python"
    raise ValueError(
        "Could not detect a supported project. Add a Python, Node.js, Java, or Go "
        "manifest at the repository root."
    )


class DockerRunner:
    """Execute a Python repository inside Docker."""

    def __init__(
        self,
        repo_path: str | Path,
        image_name: str = "cicd-project-runner",
        timeout: int = 120,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.image_name = f"{image_name}-{uuid4().hex[:8]}"
        self.timeout = timeout

    def run(self) -> dict[str, Any]:
        """Build and execute the repository inside Docker."""

        try:
            project_type = detect_project_type(self.repo_path)
        except ValueError as exc:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "logs": str(exc),
                "error": str(exc),
            }

        validation_error = self._validate_environment()

        if validation_error:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "logs": "",
                "error": validation_error,
            }

        dockerfile = self._create_dockerfile(project_type)

        try:
            build_result = self._build_image(dockerfile)

            if build_result["returncode"] != 0:
                logs = self._combine_logs(
                    build_result["stdout"],
                    build_result["stderr"],
                )

                return {
                    "success": False,
                    "exit_code": build_result["returncode"],
                    "stdout": build_result["stdout"],
                    "stderr": build_result["stderr"],
                    "logs": logs,
                    "error": "Docker image build failed.",
                    "project_type": project_type,
                }

            run_result = self._run_container()

            logs = self._combine_logs(
                run_result["stdout"],
                run_result["stderr"],
            )

            return {
                "success": run_result["returncode"] == 0,
                "exit_code": run_result["returncode"],
                "stdout": run_result["stdout"],
                "stderr": run_result["stderr"],
                "logs": logs,
                "error": (
                    None
                    if run_result["returncode"] == 0
                    else "Repository tests failed."
                ),
                "project_type": project_type,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "logs": "",
                "error": (
                    f"Docker execution exceeded "
                    f"{self.timeout} seconds."
                ),
                "project_type": project_type,
            }

        except Exception as exc:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "logs": "",
                "error": f"Docker runner error: {exc}",
                "project_type": project_type,
            }

        finally:
            self._remove_dockerfile(dockerfile)
            subprocess.run(
            ["docker", "image", "rm", self.image_name],
            capture_output=True,
            text=True,
            check=False,
            )

    def _validate_environment(self) -> str | None:
        """Validate Docker and repository availability."""

        if not self.repo_path.exists():
            return (
                f"Repository does not exist: "
                f"{self.repo_path}"
            )

        if not self.repo_path.is_dir():
            return (
                f"Repository path is not a directory: "
                f"{self.repo_path}"
            )

        if shutil.which("docker") is None:
            return (
                "Docker executable was not found. "
                "Make sure Docker Desktop is installed and running."
            )

        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )

            if result.returncode != 0:
                return (
                    "Docker is installed but the Docker daemon "
                    "is not available. Start Docker Desktop."
                )

        except Exception as exc:
            return (
                f"Unable to communicate with Docker: {exc}"
            )

        return None

    def _create_dockerfile(self, project_type: str) -> Path:
        """Create a temporary Dockerfile for the detected test runtime."""

        dockerfile = self.repo_path / f"Dockerfile.cicd-{uuid4().hex[:8]}"
        configurations = {
            "python": """FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN if [ -f Pipfile ]; then pip install --no-cache-dir pipenv && pipenv install --system --dev; elif [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi && if [ -f setup.py ] || grep -q '^\\[project\\]\\|^\\[build-system\\]' pyproject.toml 2>/dev/null; then pip install --no-cache-dir -e .; fi && pip install --no-cache-dir pytest
CMD ["python", "-m", "pytest", "-q"]
""",
            "node": """FROM node:22-bookworm-slim
WORKDIR /app
COPY . /app
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
CMD ["npm", "test"]
""",
            "go": """FROM golang:1.25-alpine
WORKDIR /app
COPY . /app
CMD ["go", "test", "./..."]
""",
        }
        if project_type == "java":
            if (self.repo_path / "pom.xml").is_file():
                content = """FROM maven:3.9-eclipse-temurin-17
WORKDIR /app
COPY . /app
CMD ["mvn", "-B", "test"]
"""
            else:
                content = """FROM gradle:8-jdk17
WORKDIR /app
COPY . /app
CMD ["sh", "-c", "if [ -f gradlew ]; then chmod +x gradlew && ./gradlew test --no-daemon; else gradle test --no-daemon; fi"]
"""
        else:
            content = configurations[project_type]

        dockerfile.write_text(
            content,
            encoding="utf-8",
        )

        return dockerfile

    def _build_image(
        self,
        dockerfile: Path,
    ) -> dict[str, Any]:
        """Build the temporary Docker image."""

        command = [
            "docker",
            "build",
            "--no-cache",
            "-f",
            dockerfile.name,
            "-t",
            self.image_name,
            ".",
        ]

        result = subprocess.run(
            command,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _run_container(self) -> dict[str, Any]:
        """Run repository tests inside Docker."""

        command = [
            "docker",
            "run",
            "--rm",
            "-e",
            "PYTHONPATH=/app",
            self.image_name,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    @staticmethod
    def _combine_logs(
        stdout: str,
        stderr: str,
    ) -> str:
        """Combine stdout and stderr into one log stream."""

        parts = []

        if stdout.strip():
            parts.append(stdout.strip())

        if stderr.strip():
            parts.append(stderr.strip())

        return "\n".join(parts)

    @staticmethod
    def _remove_dockerfile(
        dockerfile: Path,
    ) -> None:
        """Remove the temporary Dockerfile."""

        try:
            if dockerfile.exists():
                dockerfile.unlink()
        except OSError:
            pass