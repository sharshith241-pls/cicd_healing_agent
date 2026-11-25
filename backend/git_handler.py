from pathlib import Path
import subprocess
import os
from dotenv import load_dotenv

load_dotenv()
from urllib.parse import quote, urlparse, urlunparse


def clone_repo(repo_url: str, path: str | Path, branch: str | None = None) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    command = ["git", "clone"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([repo_url, str(destination)])
    
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        logs = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        raise RuntimeError(logs or "Failed to clone repository.")


def _run_git_command(repo_path: str | Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(repo_path), *args]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def checkout_new_branch(repo_path: str | Path, branch_name: str) -> None:
    result = _run_git_command(repo_path, ["checkout", "-b", branch_name])
    if result.returncode != 0:
        logs = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        raise RuntimeError(logs or "Failed to create branch.")


def commit_all_changes(repo_path: str | Path, commit_message: str) -> None:
    add_result = _run_git_command(repo_path, ["add", "-A"])
    if add_result.returncode != 0:
        logs = "\n".join(part for part in [add_result.stdout, add_result.stderr] if part).strip()
        raise RuntimeError(logs or "Failed to stage changes.")

    diff_result = _run_git_command(repo_path, ["diff", "--cached", "--quiet"])
    if diff_result.returncode == 0:
        raise RuntimeError("No changes to commit.")

    author_name = os.getenv("CICD_GIT_USER_NAME") or "CICD Healing Agent"
    author_email = (
        os.getenv("CICD_GIT_USER_EMAIL") or "cicd-healing-agent@localhost"
    )
    commit_result = _run_git_command(
        repo_path,
        [
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            commit_message,
        ],
    )
    if commit_result.returncode != 0:
        logs = "\n".join(part for part in [commit_result.stdout, commit_result.stderr] if part).strip()
        raise RuntimeError(logs or "Failed to commit changes.")


def _build_authenticated_url(remote_url: str, github_token: str) -> str:
    parsed = urlparse(remote_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Only HTTPS remote URLs are supported for token-based push.")

    host = parsed.netloc.split("@")[-1]
    safe_token = quote(github_token, safe="")
    auth_netloc = f"x-access-token:{safe_token}@{host}"

    return urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))


def push_branch(repo_path: str | Path, branch_name: str, github_token: str) -> None:
    remote_result = _run_git_command(repo_path, ["remote", "get-url", "origin"])
    if remote_result.returncode != 0:
        logs = "\n".join(part for part in [remote_result.stdout, remote_result.stderr] if part).strip()
        raise RuntimeError(logs or "Failed to resolve origin remote URL.")

    remote_url = remote_result.stdout.strip()
    authenticated_url = _build_authenticated_url(remote_url, github_token)

    push_result = subprocess.run(
        ["git", "-C", str(repo_path), "push", authenticated_url, f"HEAD:{branch_name}"],
        capture_output=True,
        text=True,
        check=False,
    )

    if push_result.returncode != 0:
        logs = "\n".join(part for part in [push_result.stdout, push_result.stderr] if part).strip()
        if (
            "403" in logs
            or ("permission to " in logs.lower() and " denied" in logs.lower())
            or "write access to repository not granted" in logs.lower()
        ):
            raise RuntimeError(
                "GitHub denied the push. The GitHub account for GITHUB_TOKEN "
                "needs write access to this repository. For a fine-grained "
                "token, grant access to this repository and Contents: Read and "
                "write; also grant Pull requests: Read and write to create a "
                "PR. A classic token needs the repo scope. Update GITHUB_TOKEN "
                "in the local .env and restart local_runner.py.\n"
                f"GitHub response: {logs}"
            )
        raise RuntimeError(logs or "Failed to push branch.")
