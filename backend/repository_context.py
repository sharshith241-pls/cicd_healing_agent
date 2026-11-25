from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


EXCLUDED_DIRECTORIES = {
    ".git",
    ".next",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}

MAX_SOURCE_FILES = 80
MAX_FILE_BYTES = 48_000
MAX_TOTAL_BYTES = 160_000
EXCLUDED_SUFFIXES = {
    ".7z",
    ".a",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lockb",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".wasm",
    ".webp",
    ".zip",
}


def collect_repository_sources(
    repo_path: str | Path,
    target_file: str | None = None,
) -> dict[str, str]:
    """Collect bounded source context while excluding credentials and build output."""

    repository = Path(repo_path).resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"Repository does not exist: {repository}")

    target_path = None
    if target_file and target_file != "repository (auto-detected)":
        target_path = _resolve_repository_file(repository, target_file)
        if not target_path.is_file():
            raise FileNotFoundError(f"Target file does not exist: {target_file}")
        if _is_sensitive(target_path) or _is_excluded(target_path, repository):
            raise ValueError("Target file is excluded because it may contain secrets or generated files.")
        if target_path.suffix.lower() in EXCLUDED_SUFFIXES:
            raise ValueError("Target file is binary and cannot be sent as text.")

    candidates = []
    for current_dir, directories, filenames in os.walk(
        repository,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current_dir)
        directories[:] = sorted(
            name
            for name in directories
            if name.lower() not in EXCLUDED_DIRECTORIES
            and not (current_path / name).is_symlink()
        )
        for filename in filenames:
            path = current_path / filename
            if _is_sensitive(path) or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            candidates.append(path)

    candidates.sort(key=lambda path: path.relative_to(repository).as_posix())
    if target_path is not None:
        candidates = [target_path] + [path for path in candidates if path != target_path]

    sources: dict[str, str] = {}
    total_bytes = 0
    for path in candidates:
        resolved_path = path.resolve()
        if repository not in resolved_path.parents:
            continue
        try:
            with resolved_path.open("rb") as source_file:
                encoded_content = source_file.read(MAX_FILE_BYTES + 1)
            if len(encoded_content) > MAX_FILE_BYTES:
                continue
            content = encoded_content.decode("utf-8")
        except (OSError, UnicodeError):
            continue

        if total_bytes + len(encoded_content) > MAX_TOTAL_BYTES:
            continue

        relative_path = path.relative_to(repository).as_posix()
        sources[relative_path] = content
        total_bytes += len(encoded_content)
        if len(sources) >= MAX_SOURCE_FILES:
            break

    if target_path is not None:
        target_relative = target_path.relative_to(repository).as_posix()
        if target_relative not in sources:
            raise ValueError("Target file is not a supported, readable text file.")

    if not sources:
        raise ValueError("No readable source files were found in the repository.")
    return sources


def apply_file_changes(
    repo_path: str | Path,
    changes: dict[str, str],
    allowed_paths: set[str],
) -> list[str]:
    """Apply changes only to existing files included in the repair context."""

    repository = Path(repo_path).resolve()
    validated: list[tuple[str, Path, str]] = []
    for relative_path, content in changes.items():
        if not isinstance(relative_path, str) or not isinstance(content, str):
            raise ValueError("File changes must map repository paths to text.")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES * 4:
            raise ValueError(f"AI returned an oversized file: {relative_path}")

        path = _resolve_repository_file(repository, relative_path)
        normalized = path.relative_to(repository).as_posix()
        if normalized not in allowed_paths:
            raise ValueError(f"AI requested a file outside the supplied context: {relative_path}")
        if not path.is_file() or _is_sensitive(path):
            raise ValueError(f"AI requested an unavailable or excluded file: {relative_path}")

        validated.append((normalized, path, content))

    if not validated:
        raise ValueError("AI returned no applicable file changes.")

    applied: list[str] = []
    for normalized, path, content in validated:
        path.write_text(content, encoding="utf-8")
        applied.append(normalized)
    return applied


def _resolve_repository_file(repository: Path, relative_path: str) -> Path:
    pure_path = PurePosixPath(relative_path.replace("\\", "/"))
    if pure_path.is_absolute() or not pure_path.parts or ".." in pure_path.parts:
        raise ValueError("Target paths must stay inside the repository.")
    path = (repository / Path(*pure_path.parts)).resolve()
    if repository not in path.parents:
        raise ValueError("Target paths must stay inside the repository.")
    return path


def _is_excluded(path: Path, repository: Path) -> bool:
    relative_parts = path.relative_to(repository).parts
    return any(part.lower() in EXCLUDED_DIRECTORIES for part in relative_parts)


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in {".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
        or any(
            token in name
            for token in (
                "secret",
                "credential",
                "token",
                "service-account",
                "service_account",
                "serviceaccount",
            )
        )
        or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}
    )
