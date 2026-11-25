from types import SimpleNamespace

from backend import main


def test_docker_status_reports_ready_engine(monkeypatch):
    monkeypatch.setattr(main.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="28.5.1|linux",
            stderr="",
        ),
    )

    assert main.docker_status() == {
        "available": True,
        "message": "Docker Engine is ready.",
        "server_version": "28.5.1",
        "operating_system": "linux",
    }


def test_docker_status_explains_missing_docker_cli(monkeypatch):
    monkeypatch.setattr(main.shutil, "which", lambda _: None)

    result = main.docker_status()

    assert result["available"] is False
    assert "Docker CLI was not found" in result["message"]
