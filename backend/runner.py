"""
CICD Self-Healing Runner
------------------------

Connects the tested components into the actual self-healing loop:

    Repository
        ↓
    Docker Test
        ↓
    Log Processor
        ↓
    Error Analyzer
        ↓
    Failure Memory / AI
        ↓
    Apply Fix
        ↓
    Docker Re-test
        ↓
    PASS / Retry
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.ai import generate_repository_changes
from backend.docker_runner import DockerRunner, get_docker_status
from backend.error_analyzer import ErrorAnalyzer, ErrorInfo
from backend.error_database import ErrorDatabase
from backend.fix_engine import FixEngine
from backend.log_processor import LogProcessor
from backend.native_runner import NativeRunner
from backend.repository_context import (
    apply_file_changes,
    collect_repository_sources,
)

logger = logging.getLogger(__name__)


def run_tests(repo_path: str | Path) -> dict[str, object]:
    """Run tests in Docker when available, otherwise directly on this machine."""

    docker_status = get_docker_status()
    if docker_status["available"]:
        runner = DockerRunner(repo_path)
        runner_mode = "docker"
        runner_message = "Docker is available; tests run in an isolated container."
    else:
        runner = NativeRunner(repo_path)
        runner_mode = "native"
        runner_message = (
            f"Docker is unavailable ({docker_status['message']}); running tests "
            "directly on this computer without container isolation. Only run "
            "repositories you trust."
        )

    result = runner.run()

    return {
        "success": result["success"],
        "output": f"[RUNNER] {runner_message}\n{result['logs']}",
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "error": result["error"],
        "project_type": result.get("project_type"),
        "runner_mode": runner_mode,
    }


def _build_error_info(test_output: str) -> ErrorInfo | None:
    """Convert processed pytest output into ErrorInfo."""

    parsed = LogProcessor.process(test_output)

    filtered_log = str(parsed["filtered_log"] or test_output)
    if not test_output.strip():
        return None

    error_type = str(parsed["error_type"] or "TestFailure")

    message = str(
        parsed["message"]
        or next(
            (line.strip() for line in reversed(filtered_log.splitlines()) if line.strip()),
            "Unknown test failure",
        )[:1000]
    )

    stack_trace = filtered_log

    file_path = parsed["file"]

    error_hash = ErrorAnalyzer.extract_error_hash(
        message,
        error_type,
    )

    return ErrorInfo(
        error_type=error_type,
        error_message=message,
        stack_trace=stack_trace,
        file_path=str(file_path) if file_path else None,
        error_hash=error_hash,
    )


def self_heal_repository(
    repo_path: str | Path,
    target_file: str | None = None,
    repo_url: str = "local://demo",
    max_attempts: int = 3,
    database_url: str = "sqlite:///./workspace/cicd_errors.db",
) -> dict[str, Any]:

    repository = Path(repo_path).resolve()

    logs: list[str] = []

    if not repository.exists():
        return {
            "success": False,
            "fix_method": "none",
            "attempts": 0,
            "logs": f"Repository does not exist: {repository}",
        }

    # ---------------------------------------------------------------
    # DATABASE
    # ---------------------------------------------------------------

    try:
        db = ErrorDatabase(database_url)
    except Exception as exc:
        return {
            "success": False,
            "fix_method": "none",
            "attempts": 0,
            "logs": f"Database initialization failed: {exc}",
        }

    # ---------------------------------------------------------------
    # REPAIR CONTEXT
    # ---------------------------------------------------------------

    try:
        original_files = collect_repository_sources(
            repository,
            target_file,
        )
    except (OSError, ValueError) as exc:
        db.close()

        return {
            "success": False,
            "fix_method": "none",
            "attempts": 0,
            "logs": f"Failed to collect repository source files: {exc}",
        }
    allowed_paths = set(original_files)
    target_label = target_file or "repository (auto-detected)"

    latest_output = ""

    successful_method = "none"
    successful_attempt = None
    memory_used = False

    # ---------------------------------------------------------------
    # INITIAL TEST
    # ---------------------------------------------------------------

    logs.append("========================================")
    logs.append("CICD SELF-HEALING STARTED")
    logs.append("========================================")

    logs.append(f"Repository: {repository}")
    logs.append(f"Target context: {target_label}")
    logs.append("")

    logs.append("[1] Running initial tests with the local auto-runner...")

    initial_result = run_tests(repository)
    logs.append(str(initial_result["output"]).splitlines()[0])
    if initial_result.get("project_type"):
        logs.append(f"[DETECT] Project type: {initial_result['project_type']}")

    latest_output = str(
        initial_result["output"]
    )

    if initial_result["exit_code"] == -1:
        logs.append(f"[RUNNER ERROR] {initial_result['error']}")
        db.close()
        return {
            "success": False,
            "fix_method": "none",
            "attempts": 0,
            "memory_used": False,
            "logs": "\n".join(logs),
        }

    if initial_result["success"]:

        logs.append(
            "[PASS] Repository tests already pass."
        )

        db.close()

        return {
            "success": True,
            "fix_method": "none",
            "attempts": 0,
            "memory_used": False,
            "logs": "\n".join(logs),
        }

    logs.append(
        "[FAIL] Initial tests failed."
    )

    # ---------------------------------------------------------------
    # FIX ENGINE
    # ---------------------------------------------------------------

    fix_engine = FixEngine(
        db=db,
        ai_generator=generate_repository_changes,
    )

    # ---------------------------------------------------------------
    # RETRY LOOP
    # ---------------------------------------------------------------

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        logs.append("")
        logs.append(
            f"========== ATTEMPT {attempt}/{max_attempts} =========="
        )

        # -----------------------------------------------------------
        # PROCESS LOG
        # -----------------------------------------------------------

        processed = LogProcessor.process(
            latest_output
        )

        logs.append(
            f"[LOG] Raw log size: "
            f"{processed['raw_log_size']} characters"
        )

        logs.append(
            f"[LOG] Filtered log size: "
            f"{processed['filtered_log_size']} characters"
        )

        raw_size = processed["raw_log_size"]
        filtered_size = processed["filtered_log_size"]

        if raw_size:
            reduction = (
                (raw_size - filtered_size)
                / raw_size
                * 100
            )
        else:
            reduction = 0.0

        logs.append(
            f"[LOG] Noise reduction: "
            f"{reduction:.1f}%"
        )

        logs.append(
            f"[ERROR] Type: "
            f"{processed['error_type']}"
        )

        logs.append(
            f"[ERROR] Message: "
            f"{processed['message']}"
        )

        logs.append(
            f"[ERROR] File: "
            f"{processed['file']}"
        )

        logs.append(
            f"[ERROR] Line: "
            f"{processed['line']}"
        )

        logs.append(
            f"[ERROR] Test: "
            f"{processed['test']}"
        )

        # -----------------------------------------------------------
        # BUILD ERROR INFO
        # -----------------------------------------------------------

        error_info = _build_error_info(
            latest_output
        )

        if error_info is None:

            logs.append(
                "[ERROR] Could not structure the failure."
            )

            break

        logs.append(
            f"[ANALYZER] Error hash: "
            f"{error_info.error_hash}"
        )

        # -----------------------------------------------------------
        # FIX ENGINE
        # -----------------------------------------------------------

        try:

            fix_result = fix_engine.get_or_create_fix(
                error_info=error_info,
                repo_url=repo_url,
                target_file=target_label,
                log_output=latest_output,
                attempt=attempt,
                max_attempts=max_attempts,
                repo_path=repository,
            )

        except Exception as exc:

            logger.exception(
                "Fix engine failed"
            )

            logs.append(
                f"[FIX ENGINE ERROR] {exc}"
            )

            continue

        if not fix_result["success"]:

            logs.append(
                "[FIX] No fix generated."
            )

            logs.append(
                str(
                    fix_result.get(
                        "details",
                        "Unknown fix failure",
                    )
                )
            )

            continue

        fix_method = str(
            fix_result["fix_method"]
        )

        fix_code = fix_result.get(
            "fix_code"
        )

        if not isinstance(fix_code, dict) or not fix_code:

            logs.append(
                "[FIX] Fix engine returned empty code."
            )

            continue

        successful_method = fix_method

        if fix_method == "cache":

            memory_used = True

            logs.append(
                "[MEMORY] Known successful fix found."
            )

            logs.append(
                f"[MEMORY] Confidence: "
                f"{float(fix_result['confidence']) * 100:.1f}%"
            )

        elif fix_method == "ai":

            logs.append(
                "[AI] No reusable fix found."
            )

            logs.append(
                "[AI] OpenRouter generated a new fix."
            )

        elif fix_method == "deep_ai":

            logs.append(
                "[DEEP AI] Using deeper context analysis."
            )

        logs.append(
            f"[FIX] Method: {fix_method}"
        )

        # -----------------------------------------------------------
        # APPLY FIX
        # -----------------------------------------------------------

        try:

            changed_files = apply_file_changes(
                repository,
                fix_code,
                allowed_paths,
            )

        except (OSError, ValueError) as exc:

            logs.append(
                f"[FIX] Failed to write fix: {exc}"
            )

            continue

        logs.append(
            "[FIX] Applied changes to: "
            + ", ".join(changed_files)
        )

        # -----------------------------------------------------------
        # RE-TEST
        # -----------------------------------------------------------

        logs.append("[2] Re-running tests with the local auto-runner...")

        retest_result = run_tests(
            repository
        )

        latest_output = str(
            retest_result["output"]
        )

        if retest_result["exit_code"] == -1:
            logs.append(f"[RUNNER ERROR] {retest_result['error']}")
            break

        if retest_result["success"]:

            logs.append(
                "[PASS] Tests passed after fix."
            )

            fix_id = fix_result.get(
                "fix_id"
            )

            if fix_id:
                db.update_fix_success(
                    int(fix_id),
                    True,
                )

            successful_attempt = attempt

            logs.append(
                "========================================"
            )

            logs.append(
                "CICD SELF-HEALING SUCCESSFUL"
            )

            logs.append(
                "========================================"
            )

            db.close()

            return {
                "success": True,
                "fix_method": successful_method,
                "attempts": successful_attempt,
                "memory_used": memory_used,
                "error_type": error_info.error_type,
                "error_message": error_info.error_message,
                "target_file": target_label,
                "logs": "\n".join(logs),
            }

        # -----------------------------------------------------------
        # FIX FAILED
        # -----------------------------------------------------------

        logs.append(
            "[FAIL] Tests still failing."
        )

        fix_id = fix_result.get(
            "fix_id"
        )

        if fix_id:
            db.update_fix_success(
                int(fix_id),
                False,
            )

        logs.append(
            "[RETRY] Preparing next attempt."
        )

    # ---------------------------------------------------------------
    # ALL ATTEMPTS FAILED
    # ---------------------------------------------------------------

    try:

        apply_file_changes(
            repository,
            original_files,
            allowed_paths,
        )

        logs.append(
            "[RESTORE] Restored original repository source files."
        )

    except (OSError, ValueError) as exc:

        logs.append(
            f"[RESTORE ERROR] {exc}"
        )

    logs.append(
        "========================================"
    )

    logs.append(
                "CICD SELF-HEALING FAILED"
    )

    logs.append(
        "========================================"
    )

    db.close()

    return {
        "success": False,
        "fix_method": successful_method,
        "attempts": max_attempts,
        "memory_used": memory_used,
        "target_file": target_label,
        "logs": "\n".join(logs),
    }