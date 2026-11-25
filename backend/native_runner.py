"""Run supported project test commands directly on the local machine."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.docker_runner import DockerRunner, detect_project_type


class NativeRunner:
    """Run tests using locally installed language runtimes without isolation."""

    def __init__(self, repo_path: str | Path, timeout: int = 120):
        self.repo_path = Path(repo_path).resolve()
        self.timeout = timeout

    def run(self) -> dict[str, Any]:
        try:
            project_type = detect_project_type(
                self.repo_path,
                prefer_dockerfile=False,
            )
            command = self._test_command(project_type)
        except ValueError as exc:
            if (self.repo_path / "Dockerfile").is_file():
                return self._failure(
                    "This repository only defines a custom Dockerfile test "
                    "command, which cannot run without Docker."
                )
            return self._failure(str(exc))

        executable = command[0]
        if not Path(executable).is_absolute():
            resolved_executable = shutil.which(executable)
            if resolved_executable is None:
                return self._failure(
                    f"Required local runtime or test command was not found: {executable}."
                )
            command[0] = resolved_executable

        try:
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._failure(
                f"Local test execution exceeded {self.timeout} seconds.",
                project_type=project_type,
            )
        except OSError as exc:
            return self._failure(
                f"Unable to start the local test command: {exc}",
                project_type=project_type,
            )

        logs = DockerRunner._combine_logs(result.stdout, result.stderr)
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "logs": logs,
            "error": None if result.returncode == 0 else "Repository tests failed.",
            "project_type": project_type,
            "runner_mode": "native",
        }

    def _test_command(self, project_type: str) -> list[str]:
        if project_type == "python":
            return [sys.executable, "-m", "pytest", "-q"]
        if project_type == "node":
            return ["npm", "test"]
        if project_type == "go":
            return ["go", "test", "./..."]
        if project_type == "java":
            if (self.repo_path / "pom.xml").is_file():
                return ["mvn", "-B", "test"]
            return self._gradle_command()
        raise ValueError(
            "This repository requires its custom Dockerfile and cannot run "
            "without Docker. Use a supported Python, Node.js, Java, or Go project."
        )

    def _gradle_command(self) -> list[str]:
        if sys.platform == "win32":
            wrapper = self.repo_path / "gradlew.bat"
            if wrapper.is_file():
                return ["cmd.exe", "/d", "/c", "gradlew.bat", "test", "--no-daemon"]
        else:
            wrapper = self.repo_path / "gradlew"
            if wrapper.is_file():
                return ["./gradlew", "test", "--no-daemon"]
        return ["gradle", "test", "--no-daemon"]

    @staticmethod
    def _failure(message: str, project_type: str | None = None) -> dict[str, Any]:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "logs": message,
            "error": message,
            "project_type": project_type,
            "runner_mode": "native",
        }
