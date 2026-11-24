from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from backend.error_analyzer import ErrorInfo
from backend.error_database import ErrorDatabase

logger = logging.getLogger(__name__)


class FixEngine:

    def __init__(self, db: ErrorDatabase, ai_generator):
        self.db = db
        self.ai_generator = ai_generator

    def get_or_create_fix(
        self,
        error_info: ErrorInfo,
        repo_url: str,
        target_file: str,
        log_output: str,
        attempt: int = 1,
        max_attempts: int = 3,
        repo_path: str | Path | None = None,
    ) -> dict:

        cache_result = self._cache_lookup(error_info, target_file)

        if cache_result["found"]:
            logger.info(
                "[MEMORY] Known successful fix found."
            )

            return {
                "success": True,
                "fix_code": cache_result["fix_code"],
                "fix_method": "cache",
                "confidence": min(
                    cache_result["success_rate"],
                    0.95,
                ),
                "error_id": cache_result["error_id"],
                "fix_id": cache_result["fix_id"],
                "details": "Reused cached successful fix.",
            }

        if repo_path is None:
            return {
                "success": False,
                "fix_code": None,
                "fix_method": "none",
                "confidence": 0.0,
                "error_id": None,
                "fix_id": None,
                "details": "Repository filesystem path was not provided.",
            }

        repo_path = Path(repo_path).resolve()

        if not repo_path.exists():
            return {
                "success": False,
                "fix_code": None,
                "fix_method": "none",
                "confidence": 0.0,
                "error_id": None,
                "fix_id": None,
                "details": f"Repository does not exist: {repo_path}",
            }

        existing_error = None

        if error_info.error_hash:
            existing_error = self.db.get_error_by_hash(
                error_info.error_hash
            )

        if existing_error:
            error_id = existing_error["id"]
        else:
            error_id = self.db.store_error(
                error_hash=(
                    error_info.error_hash
                    or self._fallback_hash(error_info)
                ),
                error_type=error_info.error_type,
                error_message=error_info.error_message,
                stack_trace=error_info.stack_trace,
                repo_url=repo_url,
                file_path=target_file,
            )

        ai_result = self._ai_fix(
            error_info=error_info,
            repo_url=repo_url,
            target_file=target_file,
            log_output=log_output,
            error_id=error_id,
            repo_path=repo_path,
        )

        if ai_result["success"]:
            return ai_result

        if attempt < max_attempts:
            deep_result = self._deep_ai_fix(
                error_info=error_info,
                repo_url=repo_url,
                target_file=target_file,
                log_output=log_output,
                error_id=error_id,
                attempt=attempt,
                repo_path=repo_path,
            )

            if deep_result["success"]:
                return deep_result

        return {
            "success": False,
            "fix_code": None,
            "fix_method": "none",
            "confidence": 0.0,
            "error_id": error_id,
            "fix_id": None,
            "details": (
                f"Could not generate fix after "
                f"{max_attempts} attempts"
            ),
        }

    def _cache_lookup(
        self,
        error_info: ErrorInfo,
        target_file: str,
    ) -> dict:

        if not error_info.error_hash:
            return {
                "found": False,
                "fix_code": None,
                "success_rate": 0.0,
                "error_id": None,
                "fix_id": None,
            }

        error_record = self.db.get_error_by_hash(
            error_info.error_hash
        )

        if not error_record:
            return {
                "found": False,
                "fix_code": None,
                "success_rate": 0.0,
                "error_id": None,
                "fix_id": None,
            }

        error_id = error_record["id"]

        fix = self.db.get_fix_for_error(error_id)

        if not fix:
            return {
                "found": False,
                "fix_code": None,
                "success_rate": 0.0,
                "error_id": error_id,
                "fix_id": None,
            }

        success_rate = float(
            fix.get("success_rate", 0.0) or 0.0
        )

        if success_rate < 0.5:
            return {
                "found": False,
                "fix_code": None,
                "success_rate": success_rate,
                "error_id": error_id,
                "fix_id": fix["id"],
            }

        try:
            fix_changes = json.loads(fix["fixed_code"])
        except (TypeError, json.JSONDecodeError):
            fix_changes = None

        if not isinstance(fix_changes, dict):
            if target_file == "repository (auto-detected)":
                return {
                    "found": False,
                    "fix_code": None,
                    "success_rate": success_rate,
                    "error_id": error_id,
                    "fix_id": fix["id"],
                }
            fix_changes = {target_file: fix["fixed_code"]}

        if any(not isinstance(path, str) or not isinstance(code, str) for path, code in fix_changes.items()):
            return {
                "found": False,
                "fix_code": None,
                "success_rate": success_rate,
                "error_id": error_id,
                "fix_id": fix["id"],
            }

        return {
            "found": True,
            "fix_code": fix_changes,
            "success_rate": success_rate,
            "error_id": error_id,
            "fix_id": fix["id"],
        }

    def _ai_fix(
        self,
        error_info: ErrorInfo,
        repo_url: str,
        target_file: str,
        log_output: str,
        error_id: int,
        repo_path: Path,
    ) -> dict:

        try:

            fix_changes = self.ai_generator(
                file_path=target_file,
                repo_path=repo_path,
                test_output=log_output,
            )

            if not fix_changes:
                raise RuntimeError(
                    "AI returned no file changes."
                )

            fix_id = self.db.store_fix(
                error_id=error_id,
                fix_description="AI-generated repository fix",
                fixed_code=json.dumps(fix_changes),
                fix_method="ai",
                source="ai",
                ai_model="openrouter",
            )

            return {
                "success": True,
                "fix_code": fix_changes,
                "fix_method": "ai",
                "confidence": 0.80,
                "error_id": error_id,
                "fix_id": fix_id,
                "details": "AI-generated fix.",
            }

        except Exception:
            logger.exception(
                "[AI] Fix generation failed"
            )

            return {
                "success": False,
                "fix_code": None,
                "fix_method": "ai",
                "confidence": 0.0,
                "error_id": error_id,
                "fix_id": None,
                "details": "AI fix generation failed.",
            }

    def _deep_ai_fix(
        self,
        error_info: ErrorInfo,
        repo_url: str,
        target_file: str,
        log_output: str,
        error_id: int,
        attempt: int,
        repo_path: Path,
    ) -> dict:

        try:

            fix_changes = self.ai_generator(
                file_path=target_file,
                repo_path=repo_path,
                test_output=log_output,
            )

            if not fix_changes:
                raise RuntimeError(
                    "Deep AI returned no file changes."
                )

            fix_id = self.db.store_fix(
                error_id=error_id,
                fix_description="Deep AI-generated repository fix",
                fixed_code=json.dumps(fix_changes),
                fix_method="deep_ai",
                source="deep_ai",
                ai_model="openrouter",
            )

            return {
                "success": True,
                "fix_code": fix_changes,
                "fix_method": "deep_ai",
                "confidence": 0.85,
                "error_id": error_id,
                "fix_id": fix_id,
                "details": "Deep AI-generated fix.",
            }

        except Exception:
            logger.exception(
                "[DEEP AI] Fix generation failed"
            )

            return {
                "success": False,
                "fix_code": None,
                "fix_method": "deep_ai",
                "confidence": 0.0,
                "error_id": error_id,
                "fix_id": None,
                "details": "Deep AI generation failed.",
            }

    @staticmethod
    def _fallback_hash(
        error_info: ErrorInfo,
    ) -> str:

        value = (
            f"{error_info.error_type}|"
            f"{error_info.error_message}"
        )

        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()