import subprocess

import pytest

from backend import git_handler
from backend.git_handler import commit_all_changes, push_branch


def _init_repository(path):
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    (path / "change.txt").write_text("repaired\n", encoding="utf-8")


def test_commit_uses_pipeline_identity_when_git_identity_is_not_configured(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    _init_repository(repository)
    monkeypatch.delenv("CICD_GIT_USER_NAME", raising=False)
    monkeypatch.delenv("CICD_GIT_USER_EMAIL", raising=False)

    commit_all_changes(repository, "Apply repair")

    author = subprocess.run(
        ["git", "-C", str(repository), "log", "-1", "--format=%an <%ae>"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert author == "CICD Healing Agent <cicd-healing-agent@localhost>"


def test_commit_uses_configured_pipeline_identity(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    _init_repository(repository)
    monkeypatch.setenv("CICD_GIT_USER_NAME", "Local Repair Bot")
    monkeypatch.setenv("CICD_GIT_USER_EMAIL", "repair@example.com")

    commit_all_changes(repository, "Apply repair")

    author = subprocess.run(
        ["git", "-C", str(repository), "log", "-1", "--format=%an <%ae>"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert author == "Local Repair Bot <repair@example.com>"


def test_push_permission_error_explains_required_github_access(monkeypatch, tmp_path):
    monkeypatch.setattr(
        git_handler,
        "_run_git_command",
        lambda *_: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="https://github.com/owner/repo.git\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        git_handler.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=128,
            stdout="",
            stderr=(
                "remote: Permission to owner/repo.git denied to account.\n"
                "fatal: unable to access URL: The requested URL returned error: 403"
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Contents: Read and write") as exc:
        push_branch(tmp_path, "cicd-fix-test", "not-a-real-token")

    assert "restart local_runner.py" in str(exc.value)
    assert "Permission to owner/repo.git denied" in str(exc.value)
