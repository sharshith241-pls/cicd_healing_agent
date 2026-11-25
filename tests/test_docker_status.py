from types import SimpleNamespace

from backend import main
from backend.docker_runner import get_docker_status


def test_docker_status_reports_ready_engine(monkeypatch):
    monkeypatch.setattr("backend.docker_runner.shutil.which", lambda _: "docker")
    monkeypatch.setattr(
        "backend.docker_runner.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="28.5.1|linux",
            stderr="",
        ),
    )

    assert get_docker_status() == {
        "available": True,
        "message": "Docker Engine is ready.",
        "server_version": "28.5.1",
        "operating_system": "linux",
    }


def test_runner_status_recommends_native_mode_when_docker_is_missing(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_docker_status",
        lambda: {"available": False, "message": "Docker CLI was not found."},
    )

    status = main.runner_status()

    assert status["available"] is True
    assert status["mode"] == "native"
    assert "without container isolation" in status["message"]
