import json

import pytest

from backend import ai
from backend.docker_runner import DockerRunner, detect_project_type
from backend.repository_context import (
    apply_file_changes,
    collect_repository_sources,
)
from backend.runner import _build_error_info


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"requirements.txt": ""}, "python"),
        ({"package.json": json.dumps({"scripts": {"test": "node test.js"}})}, "node"),
        ({"pom.xml": "<project/>"}, "java"),
        ({"go.mod": "module example.test/app"}, "go"),
        ({"build.gradle": "plugins {}"}, "java"),
    ],
)
def test_detects_project_runtime(tmp_path, files, expected):
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    assert detect_project_type(tmp_path) == expected


def test_node_requires_a_test_script(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="scripts.test"):
        detect_project_type(tmp_path)


def test_custom_dockerfile_is_used_without_being_removed(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM rust:1\nCMD [\"cargo\", \"test\"]\n",
        encoding="utf-8",
    )
    runner = DockerRunner(tmp_path)

    assert detect_project_type(tmp_path) == "custom"
    assert runner._create_dockerfile("custom") == dockerfile
    runner._remove_dockerfile(dockerfile)
    assert dockerfile.exists()


def test_dockerfile_uses_detected_runtime(tmp_path):
    runner = DockerRunner(tmp_path)
    dockerfile = runner._create_dockerfile("go")
    try:
        assert "FROM golang:" in dockerfile.read_text(encoding="utf-8")
        assert 'CMD ["go", "test", "./..."]' in dockerfile.read_text(encoding="utf-8")
    finally:
        runner._remove_dockerfile(dockerfile)


@pytest.mark.parametrize(
    ("project_type", "markers"),
    [
        ("python", ("FROM python:", "pytest")),
        ("node", ("FROM node:", '"npm", "test"')),
        ("java", ("FROM maven:", "mvn")),
        ("go", ("FROM golang:", '"go", "test"')),
    ],
)
def test_dockerfile_has_runtime_specific_setup(tmp_path, project_type, markers):
    runner = DockerRunner(tmp_path)
    if project_type == "java":
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    dockerfile = runner._create_dockerfile(project_type)
    try:
        content = dockerfile.read_text(encoding="utf-8")
        for marker in markers:
            assert marker in content
    finally:
        runner._remove_dockerfile(dockerfile)


def test_non_python_test_failures_produce_error_context():
    info = _build_error_info("FAIL src/app.test.js\nExpected 2 but received 1")

    assert info is not None
    assert info.error_type == "TestFailure"
    assert "Expected 2" in info.error_message
    assert len(info.error_hash) == 64


def test_repository_context_and_changes_are_limited_to_source_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "lib.rs").write_text("pub fn add(a: i32, b: i32) -> i32 { a + b }\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("test:\n\tcargo test\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=do-not-read\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dependency.js").write_text("ignored", encoding="utf-8")

    sources = collect_repository_sources(tmp_path)
    assert set(sources) == {"src/app.js", "src/lib.rs", "Makefile"}
    assert apply_file_changes(
        tmp_path,
        {"src/app.js": "module.exports = 2;\n"},
        set(sources),
    ) == ["src/app.js"]
    assert (tmp_path / "src" / "app.js").read_text(encoding="utf-8") == "module.exports = 2;\n"
    with pytest.raises(ValueError, match="Target paths must stay inside the repository"):
        apply_file_changes(tmp_path, {"../outside.js": "bad"}, set(sources))


def test_repository_context_skips_oversized_files(tmp_path):
    (tmp_path / "large.rs").write_text("x" * 48_001, encoding="utf-8")
    (tmp_path / "small.rs").write_text("pub fn main() {}", encoding="utf-8")

    assert collect_repository_sources(tmp_path) == {"small.rs": "pub fn main() {}"}


def test_openrouter_changes_support_multiple_files_and_only_context_paths(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.go").write_text("package app\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.test/app\n", encoding="utf-8")
    response = json.dumps(
        {
            "src/app.go": "package app\nfunc Add(a, b int) int { return a + b }\n",
            "go.mod": "module example.test/app\n",
        }
    )
    prompts = []
    monkeypatch.setattr(ai, "_call_openrouter", lambda prompt: prompts.append(prompt) or response)

    changes = ai.generate_repository_changes(
        "repository (auto-detected)",
        tmp_path,
        "test failure",
    )

    assert set(changes) == {"src/app.go", "go.mod"}
    assert "src/app.go" in prompts[0]
    assert "go.mod" in prompts[0]


def test_openrouter_response_rejects_non_json():
    with pytest.raises(RuntimeError, match="valid JSON"):
        ai._parse_file_changes("not JSON")
