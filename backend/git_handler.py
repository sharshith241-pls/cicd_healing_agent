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

    commit_result = _run_git_command(repo_path, ["commit", "-m", commit_message])
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
        raise RuntimeError(logs or "Failed to push branch.")
