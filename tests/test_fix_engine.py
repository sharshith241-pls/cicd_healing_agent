import json

from backend.error_analyzer import ErrorInfo
from backend.error_database import ErrorDatabase
from backend.fix_engine import FixEngine


def test_cache_skips_legacy_raw_code_and_reuses_valid_hashed_fix(tmp_path):
    database = ErrorDatabase(":memory:")
    error_hash = "stable-test-error-hash"
    error_id = database.store_error(
        error_hash=error_hash,
        error_type="AssertionError",
        error_message="assert expected result",
    )
    legacy_fix_id = database.store_fix(
        error_id=error_id,
        fix_description="Legacy raw source fix",
        fixed_code="def repaired():\n    return True\n",
    )
    for _ in range(5):
        database.update_fix_success(legacy_fix_id, True)

    expected_changes = {"algorithms.py": "def repaired():\n    return True\n"}
    valid_fix_id = database.store_fix(
        error_id=error_id,
        fix_description="File-mapped fix",
        fixed_code=json.dumps(expected_changes),
    )
    database.update_fix_success(valid_fix_id, True)

    def ai_must_not_run(**_kwargs):
        raise AssertionError("AI should not run when a valid cached fix exists")

    engine = FixEngine(database, ai_must_not_run)
    result = engine.get_or_create_fix(
        error_info=ErrorInfo(
            error_type="AssertionError",
            error_message="assert expected result",
            error_hash=error_hash,
        ),
        repo_url="https://github.com/example/repository",
        target_file="repository (auto-detected)",
        log_output="test failed",
        repo_path=tmp_path,
    )

    assert result["success"] is True
    assert result["fix_method"] == "cache"
    assert result["fix_id"] == valid_fix_id
    assert result["fix_code"] == expected_changes

    database.close()
