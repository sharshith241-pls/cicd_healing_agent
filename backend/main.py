from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import json
import logging
import os
from urllib import error, request
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.ai import generate_repository_changes
from backend.git_handler import (
    checkout_new_branch,
    clone_repo,
    commit_all_changes,
    push_branch,
)
from backend.runner import run_tests
from backend.error_database import ErrorDatabase
from backend.error_analyzer import ErrorAnalyzer, ErrorInfo
from backend.fix_engine import FixEngine
from backend.repository_context import (
    apply_file_changes,
    collect_repository_sources,
)


# ============================================================================
# ENVIRONMENT
# ============================================================================

load_dotenv()


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# FASTAPI
# ============================================================================

app = FastAPI(
    title="CICD Self-Healing Pipeline",
    description="Autonomous CI/CD failure detection and self-healing system.",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# DATABASE
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./workspace/cicd_errors.db",
)

if DB_URL.startswith("sqlite:///./"):
    DB_URL = (
        "sqlite:///"
        + str(
            PROJECT_ROOT
            / DB_URL[len("sqlite:///./"):]
        )
    )

try:
    error_db = ErrorDatabase(DB_URL)
    logger.info("Error database initialized.")
except Exception as exc:
    logger.warning(
        "Error database initialization failed: %s. "
        "Running without error memory.",
        exc,
    )
    error_db = None


# ============================================================================
# WORKSPACE
# ============================================================================

WORKSPACE_DIR = (
    Path(__file__).resolve().parent.parent / "workspace"
)

WORKSPACE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================================
# REQUEST MODELS
# ============================================================================

class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)
    branch: str | None = Field(None, min_length=1)


class FixAndPushRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)
    error_log: str | None = None
    target_file: str | None = None
    source_branch: str | None = Field(None, min_length=1)

    # Optional because .env is now supported.
    github_token: str | None = None

    branch_name: str | None = None

    commit_message: str = (
        "fix: automated repair by CICD self-healing agent"
    )

    max_attempts: int = Field(
        3,
        ge=1,
        le=5,
    )

    use_error_memory: bool = True

    create_pr: bool = True

    pr_title: str | None = None

    pr_body: str | None = None

    base_branch: str = "main"


class ErrorMemoryCheckRequest(BaseModel):
    error_type: str = Field(..., min_length=1)
    error_message: str = Field(..., min_length=1)
    stack_trace: str | None = None


class ErrorMemoryCheckResponse(BaseModel):
    error_found: bool
    fix_available: bool
    success_rate: float | None = None
    fix_code: str | None = None
    recommended_fix_method: str | None = None


# ============================================================================
# HELPERS
# ============================================================================

def _join_logs(parts: list[str]) -> str:
    return "\n\n".join(
        part for part in parts if part
    ).strip()


def _get_github_token(
    provided_token: str | None,
) -> str | None:
    if provided_token:
        return provided_token

    return os.getenv("GITHUB_TOKEN")


def _get_github_repo_info(
    repo_url: str,
) -> tuple[str, str]:
    """
    Extract owner and repository name from a GitHub URL.

    Example:
        https://github.com/user/project.git

    Returns:
        ("user", "project")
    """

    parsed = urlparse(repo_url)

    if parsed.netloc.lower() != "github.com":
        raise RuntimeError(
            "Automatic Pull Request creation currently "
            "supports GitHub repositories only."
        )

    parts = [
        part
        for part in parsed.path.strip("/").split("/")
        if part
    ]

    if len(parts) < 2:
        raise RuntimeError(
            "Invalid GitHub repository URL."
        )

    owner = parts[0]
    repository = parts[1]

    if repository.endswith(".git"):
        repository = repository[:-4]

    return owner, repository


def _create_pull_request(
    repo_url: str,
    token: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> dict[str, object]:

    owner, repository = _get_github_repo_info(
        repo_url
    )

    api_url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repository}/pulls"
    )

    payload = {
        "title": title,
        "head": head_branch,
        "base": base_branch,
        "body": body,
    }

    body_bytes = json.dumps(
        payload
    ).encode("utf-8")

    api_request = request.Request(
        api_url,
        data=body_bytes,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with request.urlopen(
            api_request,
            timeout=30,
        ) as response:

            response_data = json.loads(
                response.read().decode("utf-8")
            )

            return {
                "success": True,
                "number": response_data.get("number"),
                "url": response_data.get("html_url"),
            }

    except error.HTTPError as exc:
        details = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        return {
            "success": False,
            "error": (
                f"GitHub Pull Request API error: "
                f"{details}"
            ),
        }

    except error.URLError as exc:
        return {
            "success": False,
            "error": (
                f"GitHub connection error: {exc}"
            ),
        }


def _detect_target_file(
    error_log: str | None,
    explicit_target: str | None,
) -> str:

    if explicit_target:
        return explicit_target

    return "repository (auto-detected)"


# ============================================================================
# ROOT
# ============================================================================

@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "frontend.html")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "message": "CICD Self-Healing Pipeline backend is running.",
        "version": "1.0.0",
        "features": [
            "Docker test execution",
            "Error analysis",
            "Error memory",
            "AI repair",
            "Fix validation",
            "Git branch creation",
            "Git commit",
            "Git push",
            "GitHub Pull Request creation",
        ],
        "endpoints": {
            "ui": "/",
            "health": "/health",
            "analyze": "/analyze",
            "fix_and_push": "/fix-and-push",
            "fix_with_memory": "/fix-and-push-with-memory",
            "memory_check": "/error-memory/check",
            "memory_statistics": "/error-memory/statistics",
            "docs": "/docs",
        },
    }


# ============================================================================
# ANALYZE
# ============================================================================

@app.post("/analyze")
def analyze_repository(
    payload: AnalyzeRequest,
) -> dict[str, object]:

    job_id = str(uuid4())

    repo_path = (
        WORKSPACE_DIR / job_id
    )

    try:
        clone_repo(
            payload.repo_url,
            repo_path,
            branch=payload.branch,
        )

    except RuntimeError as exc:

        return {
            "job_id": job_id,
            "success": False,
            "error": str(exc),
            "logs": str(exc),
        }

    result = run_tests(repo_path)

    return {
        "job_id": job_id,
        "success": result["success"],
        "error": result["error"],
        "logs": result["output"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
    }


# ============================================================================
# FIX + PUSH + PR
# ============================================================================

@app.post("/fix-and-push")
def fix_and_push_repository(
    payload: FixAndPushRequest,
) -> dict[str, object]:

    job_id = str(uuid4())

    repo_path = (
        WORKSPACE_DIR / job_id
    )

    branch_name = (
        payload.branch_name
        or f"cicd-fix-{job_id[:8]}"
    )

    github_token = _get_github_token(
        payload.github_token
    )

    logs: list[str] = []

    logs.append(
        "========================================"
    )

    logs.append(
        "CICD SELF-HEALING STARTED"
    )

    logs.append(
        f"Repository: {payload.repo_url}"
    )

    # ------------------------------------------------------------------------
    # CLONE
    # ------------------------------------------------------------------------

    try:

        clone_repo(
            payload.repo_url,
            repo_path,
            branch=payload.source_branch,
        )

        logs.append(
            "[GIT] Repository cloned successfully."
        )

    except RuntimeError as exc:

        return {
            "job_id": job_id,
            "success": False,
            "pushed": False,
            "pull_request_created": False,
            "branch_name": branch_name,
            "logs": str(exc),
        }

    # ------------------------------------------------------------------------
    # TARGET FILE
    # ------------------------------------------------------------------------

    target_file = _detect_target_file(
        payload.error_log,
        payload.target_file,
    )

    logs.append(
        f"Target file: {target_file}"
    )

    # ------------------------------------------------------------------------
    # CREATE BRANCH
    # ------------------------------------------------------------------------

    if github_token:

        try:

            checkout_new_branch(
                repo_path,
                branch_name,
            )

            logs.append(
                f"[GIT] Created branch: {branch_name}"
            )

        except RuntimeError as exc:

            return {
                "job_id": job_id,
                "success": False,
                "pushed": False,
                "pull_request_created": False,
                "branch_name": branch_name,
                "logs": _join_logs(
                    logs + [
                        f"Branch creation failed: {exc}"
                    ]
                ),
            }

    else:

        logs.append(
            "[GIT] No GITHUB_TOKEN available. "
            "Push/PR disabled."
        )

    # ------------------------------------------------------------------------
    # INITIAL TESTS
    # ------------------------------------------------------------------------

    logs.append(
        "[1] Running initial tests..."
    )

    initial_tests = run_tests(
        repo_path
    )

    if initial_tests.get("project_type"):
        logs.append(
            f"[DETECT] Project type: {initial_tests['project_type']}"
        )

    logs.append(
        f"[TEST] Initial result: "
        f"{'PASS' if initial_tests['success'] else 'FAIL'}"
    )

    logs.append(
        str(initial_tests["output"])
    )

    if initial_tests["success"]:

        logs.append(
            "[PASS] Repository tests already pass."
        )

        return {
            "job_id": job_id,
            "success": True,
            "pushed": False,
            "pull_request_created": False,
            "branch_name": branch_name,
            "memory_used": False,
            "logs": _join_logs(logs),
        }

    try:
        original_files = collect_repository_sources(
            repo_path,
            None if target_file == "repository (auto-detected)" else target_file,
        )
    except (OSError, ValueError) as exc:

        return {
            "job_id": job_id,
            "success": False,
            "pushed": False,
            "pull_request_created": False,
            "branch_name": branch_name,
            "logs": _join_logs(
                logs + [
                    f"Failed to collect repository source files: {exc}"
                ]
            ),
        }

    allowed_paths = set(original_files)
    latest_test_output = str(
        initial_tests["output"]
    )

    fix_succeeded = False
    memory_used = False

    # ------------------------------------------------------------------------
    # ERROR MEMORY + AI
    # ------------------------------------------------------------------------

    if (
        error_db
        and payload.use_error_memory
    ):

        logs.append(
            "[MEMORY] Error memory enabled."
        )

        error_info = (
            ErrorAnalyzer.parse_error_from_log(
                latest_test_output
            )
        )

        if not error_info:

            error_info = ErrorInfo(
                error_type="UnknownError",
                error_message=(
                    "Test failed but "
                    "error could not be parsed."
                ),
                stack_trace=latest_test_output,
                error_hash=None,
            )

        fix_engine = FixEngine(
            error_db,
            generate_repository_changes,
        )

        for attempt in range(
            1,
            payload.max_attempts + 1,
        ):

            logs.append(
                f"========== ATTEMPT "
                f"{attempt}/"
                f"{payload.max_attempts} =========="
            )

            try:

                fix_result = (
                    fix_engine.get_or_create_fix(
                        error_info=error_info,
                        repo_url=payload.repo_url,
                        target_file=target_file,
                        log_output=latest_test_output,
                        attempt=attempt,
                        max_attempts=payload.max_attempts,
                    repo_path=repo_path,
                    )
                )

                if not fix_result["success"]:

                    logs.append(
                        "[FIX] No fix generated."
                    )

                    continue

                method = fix_result[
                    "fix_method"
                ]

                logs.append(
                    f"[FIX] Method: {method}"
                )

                if method == "cache":

                    memory_used = True

                    logs.append(
                        "[MEMORY] Reused known "
                        "successful fix."
                    )

                fixed_changes = fix_result[
                    "fix_code"
                ]

                if not isinstance(fixed_changes, dict) or not fixed_changes:

                    logs.append(
                        "[FIX] No valid file changes returned."
                    )

                    continue

                changed_files = apply_file_changes(
                    repo_path,
                    fixed_changes,
                    allowed_paths,
                )

                logs.append(
                    "[FIX] Applied changes to: "
                    + ", ".join(changed_files)
                )

                final_tests = run_tests(
                    repo_path
                )

                latest_test_output = str(
                    final_tests["output"]
                )

                if final_tests["success"]:

                    fix_succeeded = True

                    logs.append(
                        "[PASS] Tests passed after fix."
                    )

                    if fix_result.get(
                        "fix_id"
                    ):

                        error_db.update_fix_success(
                            fix_result["fix_id"],
                            True,
                        )

                    break

                logs.append(
                    "[FAIL] Tests still failing."
                )

                if fix_result.get(
                    "fix_id"
                ):

                    error_db.update_fix_success(
                        fix_result["fix_id"],
                        False,
                    )

                error_info = (
                    ErrorAnalyzer.parse_error_from_log(
                        latest_test_output
                    )
                    or error_info
                )

            except Exception as exc:

                logger.exception(
                    "Fix engine error"
                )

                logs.append(
                    f"[FIX ERROR] {exc}"
                )

    # ------------------------------------------------------------------------
    # FALLBACK: DIRECT AI
    # ------------------------------------------------------------------------

    else:

        logs.append(
            "[MEMORY] Error memory unavailable. "
            "Using direct AI repair."
        )

        for attempt in range(
            1,
            payload.max_attempts + 1,
        ):

            logs.append(
                f"========== ATTEMPT "
                f"{attempt}/"
                f"{payload.max_attempts} =========="
            )

            try:

                fixed_changes = generate_repository_changes(
                    file_path=target_file,
                    repo_path=repo_path,
                    test_output=latest_test_output,
                )

                changed_files = apply_file_changes(
                    repo_path,
                    fixed_changes,
                    allowed_paths,
                )

                logs.append(
                    "[FIX] AI changes applied to: "
                    + ", ".join(changed_files)
                )

                final_tests = run_tests(
                    repo_path
                )

                latest_test_output = str(
                    final_tests["output"]
                )

                if final_tests["success"]:

                    fix_succeeded = True

                    logs.append(
                        "[PASS] Tests passed after fix."
                    )

                    break

                logs.append(
                    "[FAIL] Tests still failing."
                )

            except Exception as exc:

                logs.append(
                    f"[AI ERROR] {exc}"
                )

    # ------------------------------------------------------------------------
    # FAILURE
    # ------------------------------------------------------------------------

    if not fix_succeeded:

        try:

            apply_file_changes(
                repo_path,
                original_files,
                allowed_paths,
            )

            logs.append(
                "[RESTORE] Restored original repository source files."
            )

        except (OSError, ValueError):

            logs.append(
                "[RESTORE] Failed to restore original source files."
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

        return {
            "job_id": job_id,
            "success": False,
            "pushed": False,
            "pull_request_created": False,
            "branch_name": branch_name,
            "memory_used": memory_used,
            "logs": _join_logs(logs),
        }

    # ------------------------------------------------------------------------
    # COMMIT + PUSH
    # ------------------------------------------------------------------------

    pushed = False
    pull_request_created = False
    pull_request_url = None
    pull_request_number = None

    if github_token:

        try:

            commit_all_changes(
                repo_path,
                payload.commit_message,
            )

            logs.append(
                "[GIT] Fix committed."
            )

            push_branch(
                repo_path,
                branch_name,
                github_token,
            )

            pushed = True

            logs.append(
                "[GIT] Fix pushed successfully."
            )

        except RuntimeError as exc:

            logs.append(
                f"[GIT ERROR] {exc}"
            )

            return {
                "job_id": job_id,
                "success": False,
                "pushed": False,
                "pull_request_created": False,
                "branch_name": branch_name,
                "memory_used": memory_used,
                "logs": _join_logs(logs),
            }

    # ------------------------------------------------------------------------
    # CREATE PULL REQUEST
    # ------------------------------------------------------------------------

    if (
        pushed
        and github_token
        and payload.create_pr
    ):

        pr_title = (
            payload.pr_title
            or "CICD: automated self-healing repair"
        )

        pr_body = (
            payload.pr_body
            or
            "## CICD Self-Healing Repair\n\n"
            "This Pull Request was automatically "
            "generated by CICD.\n\n"
            "### Workflow\n"
            "- Detected CI/test failure\n"
            "- Analyzed failure\n"
            "- Generated/retrieved repair\n"
            "- Applied repair\n"
            "- Re-ran tests inside Docker\n"
            "- Tests passed\n"
            "- Created Git branch\n"
            "- Committed repair\n"
            "- Pushed repair\n"
            "- Created this Pull Request\n"
        )

        pr_result = _create_pull_request(
            repo_url=payload.repo_url,
            token=github_token,
            head_branch=branch_name,
            base_branch=payload.base_branch,
            title=pr_title,
            body=pr_body,
        )

        if pr_result["success"]:

            pull_request_created = True

            pull_request_url = (
                pr_result.get("url")
            )

            pull_request_number = (
                pr_result.get("number")
            )

            logs.append(
                "[GITHUB] Pull Request created."
            )

            logs.append(
                f"[GITHUB] PR #{pull_request_number}"
            )

            logs.append(
                f"[GITHUB] {pull_request_url}"
            )

        else:

            logs.append(
                "[GITHUB] Pull Request creation failed:"
            )

            logs.append(
                str(pr_result.get("error"))
            )

    # ------------------------------------------------------------------------
    # SUCCESS
    # ------------------------------------------------------------------------

    logs.append(
        "========================================"
    )

    logs.append(
        "CICD SELF-HEALING SUCCESSFUL"
    )

    logs.append(
        "========================================"
    )

    return {
        "job_id": job_id,
        "success": True,
        "pushed": pushed,
        "pull_request_created": pull_request_created,
        "pull_request_number": pull_request_number,
        "pull_request_url": pull_request_url,
        "branch_name": branch_name,
        "memory_used": memory_used,
        "logs": _join_logs(logs),
    }


# ============================================================================
# ERROR MEMORY
# ============================================================================

@app.post(
    "/error-memory/check",
)
def check_error_memory(
    payload: ErrorMemoryCheckRequest,
) -> ErrorMemoryCheckResponse | dict:

    if not error_db:

        return {
            "error": (
                "Error database not initialized"
            ),
            "enabled": False,
        }

    try:

        error_hash = (
            ErrorAnalyzer.extract_error_hash(
                payload.error_message,
                payload.error_type,
            )
        )

        error_record = (
            error_db.get_error_by_hash(
                error_hash
            )
        )

        if not error_record:

            return ErrorMemoryCheckResponse(
                error_found=False,
                fix_available=False,
            )

        fix = (
            error_db.get_fix_for_error(
                error_record["id"]
            )
        )

        if (
            fix
            and fix.get("success_rate", 0)
            >= 0.90
        ):

            return ErrorMemoryCheckResponse(
                error_found=True,
                fix_available=True,
                success_rate=float(
                    fix["success_rate"]
                ),
                fix_code=fix["fixed_code"],
                recommended_fix_method=fix[
                    "fix_method"
                ],
            )

        return ErrorMemoryCheckResponse(
            error_found=True,
            fix_available=False,
            success_rate=(
                float(fix["success_rate"])
                if fix
                else None
            ),
        )

    except Exception as exc:

        logger.exception(
            "Error checking memory"
        )

        return {
            "error": str(exc),
            "enabled": True,
        }


@app.get(
    "/error-memory/statistics",
)
def get_error_statistics() -> dict:

    if not error_db:

        return {
            "error": (
                "Error database not initialized"
            )
        }

    try:

        stats = (
            error_db.get_error_statistics()
        )

        return {
            "total_errors": stats.get(
                "total_errors",
                0,
            ),
            "unique_error_types": stats.get(
                "unique_error_types",
                0,
            ),
            "total_occurrences": stats.get(
                "total_occurrences",
                0,
            ),
            "avg_occurrences": float(
                stats.get(
                    "avg_occurrences",
                    0,
                )
                or 0
            ),
            "total_fixes": stats.get(
                "total_fixes",
                0,
            ),
            "avg_fix_success_rate": float(
                stats.get(
                    "avg_success_rate",
                    0,
                )
                or 0
            ),
        }

    except Exception as exc:

        logger.exception(
            "Error getting statistics"
        )

        return {
            "error": str(exc)
        }


@app.post(
    "/fix-and-push-with-memory",
)
def fix_and_push_with_error_memory(
    payload: FixAndPushRequest,
) -> dict[str, object]:

    # The unified endpoint now handles the complete
    # memory â†’ AI â†’ validation â†’ GitHub â†’ PR flow.
    return fix_and_push_repository(
        payload
    )


# ============================================================================
# SERVER
# ============================================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
    )
