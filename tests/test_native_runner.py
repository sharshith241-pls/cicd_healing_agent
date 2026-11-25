from types import SimpleNamespace

from backend import native_runner, runner
from backend.native_runner import NativeRunner


def test_native_runner_executes_python_tests_in_repository(tmp_path, monkeypatch):
    (tmp_path / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(native_runner.subprocess, "run", fake_run)

    result = NativeRunner(tmp_path).run()

    assert result["success"] is True
    assert result["runner_mode"] == "native"
    assert captured["command"][1:] == ["-m", "pytest", "-q"]
    assert captured["kwargs"]["cwd"] == tmp_path.resolve()


def test_native_runner_explains_custom_dockerfile_requires_docker(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    result = NativeRunner(tmp_path).run()

    assert result["success"] is False
    assert result["exit_code"] == -1
    assert "cannot run without Docker" in result["error"]


def test_native_runner_uses_project_runtime_even_with_custom_dockerfile(tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        native_runner.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="1 passed", stderr=""),
    )

    result = NativeRunner(tmp_path).run()

    assert result["success"] is True
    assert result["project_type"] == "python"


def test_run_tests_automatically_uses_native_mode_without_docker(tmp_path, monkeypatch):
    (tmp_path / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "get_docker_status",
        lambda: {"available": False, "message": "daemon unavailable"},
    )
    monkeypatch.setattr(
        NativeRunner,
        "run",
        lambda self: {
            "success": True,
            "exit_code": 0,
            "stdout": "1 passed",
            "stderr": "",
            "logs": "1 passed",
            "error": None,
            "project_type": "python",
        },
    )

    result = runner.run_tests(tmp_path)

    assert result["success"] is True
    assert result["runner_mode"] == "native"
    assert "without container isolation" in result["output"]


def test_run_tests_keeps_docker_as_the_preferred_mode(tmp_path, monkeypatch):
    (tmp_path / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "get_docker_status",
        lambda: {
            "available": True,
            "message": "Docker Engine is ready.",
            "server_version": "28.5.1",
            "operating_system": "linux",
        },
    )
    monkeypatch.setattr(
        runner.DockerRunner,
        "run",
        lambda self: {
            "success": True,
            "exit_code": 0,
            "stdout": "1 passed",
            "stderr": "",
            "logs": "1 passed",
            "error": None,
            "project_type": "python",
        },
    )

    result = runner.run_tests(tmp_path)

    assert result["success"] is True
    assert result["runner_mode"] == "docker"
    assert "isolated container" in result["output"]
