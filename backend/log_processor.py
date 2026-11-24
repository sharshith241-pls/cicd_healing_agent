"""
CICD Log Processor
------------------

Converts noisy CI/CD execution logs into a compact, structured
error signal for the self-healing pipeline.

Flow:

    Raw Docker/Pytest Logs
            ↓
       Noise Removal
            ↓
      Error Extraction
            ↓
    Structured Error
            ↓
       AI / Memory
"""

from __future__ import annotations

import re
from typing import Any, Optional


class LogProcessor:
    """Process CI/CD logs and extract useful failure information."""

    NOISE_PATTERNS = [
        r"^\s*$",
        r"^=+\s*.*\s*=+$",
        r"^-+\s*.*\s*-+$",
        r"^platform\s+.+$",
        r"^cachedir:\s*.+$",
        r"^rootdir:\s*.+$",
        r"^configfile:\s*.+$",
        r"^plugins:\s*.+$",
        r"^collecting\s+\.\.\.$",
        r"^collected\s+\d+\s+items?.*$",
        r"^\s*\d+\s+passed.*$",
        r"^\s*\d+\s+failed.*$",
        r"^\s*\d+\s+skipped.*$",
        r"^\s*\d+\s+error.*$",
        r"^================",
    ]

    # ------------------------------------------------------------------
    # MAIN PROCESSOR
    # ------------------------------------------------------------------

    @classmethod
    def process(cls, log_output: str) -> dict[str, Any]:
        """Process raw CI/CD logs into structured failure information."""

        if not log_output or not log_output.strip():
            return {
                "success": False,
                "error_type": None,
                "message": None,
                "file": None,
                "line": None,
                "test": None,
                "failed_tests": [],
                "statistics": {
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "errors": 0,
                },
                "filtered_log": "",
                "raw_log_size": 0,
                "filtered_log_size": 0,
            }

        filtered_log = cls.reduce_noise(log_output)

        error_type = cls.extract_error_type(log_output)
        message = cls.extract_error_message(log_output)
        location = cls.extract_location(log_output)
        test_name = cls.extract_test_name(log_output)
        failed_tests = cls.extract_failed_tests(log_output)
        statistics = cls.get_log_statistics(log_output)

        return {
            "success": (
                statistics["failed"] == 0
                and statistics["errors"] == 0
                and error_type is None
            ),
            "error_type": error_type,
            "message": message,
            "file": location["file"],
            "line": location["line"],
            "test": test_name,
            "failed_tests": failed_tests,
            "statistics": statistics,
            "filtered_log": filtered_log,
            "raw_log_size": len(log_output),
            "filtered_log_size": len(filtered_log),
        }

    # ------------------------------------------------------------------
    # NOISE REDUCTION
    # ------------------------------------------------------------------

    @classmethod
    def reduce_noise(cls, log_output: str) -> str:
        """Remove irrelevant CI/test output while preserving useful data."""

        filtered_lines: list[str] = []

        for line in log_output.splitlines():

            if any(
                re.match(
                    pattern,
                    line,
                    re.IGNORECASE,
                )
                for pattern in cls.NOISE_PATTERNS
            ):
                continue

            stripped = line.strip()

            if not stripped:
                continue

            filtered_lines.append(line)

        return "\n".join(filtered_lines)

    # ------------------------------------------------------------------
    # ERROR TYPE
    # ------------------------------------------------------------------

    @staticmethod
    def extract_error_type(
        log_output: str,
    ) -> Optional[str]:
        """Extract Python error or exception type."""

        patterns = [
            r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\s*:",
            r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                log_output,
                re.MULTILINE,
            )

            if match:
                return match.group(1)

        if "assert " in log_output:
            return "AssertionError"

        return None

    # ------------------------------------------------------------------
    # ERROR MESSAGE
    # ------------------------------------------------------------------

    @staticmethod
    def extract_error_message(
        log_output: str,
    ) -> Optional[str]:
        """Extract the most useful error message."""

        # Pytest assertion detail:
        # E       assert -1 == 5
        match = re.search(
            r"^\s*E\s+(.+)$",
            log_output,
            re.MULTILINE,
        )

        if match:
            return match.group(1).strip()

        # Standard Python exception:
        # ValueError: invalid value
        match = re.search(
            r"(?:AssertionError|[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):\s*(.+)",
            log_output,
        )

        if match:
            return match.group(1).strip()

        # Pytest short failure:
        # FAILED test_app.py::test_add - assert -1 == 5
        match = re.search(
            r"^FAILED\s+\S+::\S+\s+-\s+(.+)$",
            log_output,
            re.MULTILINE | re.IGNORECASE,
        )

        if match:
            return match.group(1).strip()

        return None

    # ------------------------------------------------------------------
    # FILE + LINE
    # ------------------------------------------------------------------

    @staticmethod
    def extract_location(
        log_output: str,
    ) -> dict[str, Optional[Any]]:
        """Extract source/test file and line number."""

        # Example:
        # test_app.py:5: AssertionError
        match = re.search(
            r"([A-Za-z0-9_./\\-]+\.py):(\d+):",
            log_output,
        )

        if match:
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
            }

        # Example:
        # test_app.py:5
        match = re.search(
            r"([A-Za-z0-9_./\\-]+\.py):(\d+)",
            log_output,
        )

        if match:
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
            }

        return {
            "file": None,
            "line": None,
        }

    # ------------------------------------------------------------------
    # TEST NAME
    # ------------------------------------------------------------------

    @staticmethod
    def extract_test_name(
        log_output: str,
    ) -> Optional[str]:
        """Extract the failed pytest test name."""

        # Example:
        # FAILED test_app.py::test_add - assert -1 == 5
        match = re.search(
            r"^FAILED\s+\S+::([A-Za-z_][A-Za-z0-9_]*)",
            log_output,
            re.MULTILINE | re.IGNORECASE,
        )

        if match:
            return match.group(1)

        # Example:
        # __________________ test_add __________________
        match = re.search(
            r"_+\s+([A-Za-z_][A-Za-z0-9_]*)\s+_+",
            log_output,
        )

        if match:
            return match.group(1)

        return None

    # ------------------------------------------------------------------
    # FAILED TESTS
    # ------------------------------------------------------------------

    @staticmethod
    def extract_failed_tests(
        log_output: str,
    ) -> list[str]:
        """
        Extract failed pytest test identifiers.

        Only match actual pytest summary lines beginning with
        'FAILED', preventing words such as 'in' from being captured.
        """

        matches = re.findall(
            r"^FAILED\s+([^\s]+::[^\s]+)",
            log_output,
            re.MULTILINE | re.IGNORECASE,
        )

        return list(dict.fromkeys(matches))

    # ------------------------------------------------------------------
    # STATISTICS
    # ------------------------------------------------------------------

    @staticmethod
    def get_log_statistics(
        log_output: str,
    ) -> dict[str, int]:
        """Extract pytest result statistics."""

        stats = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
        }

        for line in log_output.splitlines():

            match = re.search(
                r"(\d+)\s+passed",
                line,
                re.IGNORECASE,
            )

            if match:
                stats["passed"] = int(match.group(1))

            match = re.search(
                r"(\d+)\s+failed",
                line,
                re.IGNORECASE,
            )

            if match:
                stats["failed"] = int(match.group(1))

            match = re.search(
                r"(\d+)\s+skipped",
                line,
                re.IGNORECASE,
            )

            if match:
                stats["skipped"] = int(match.group(1))

            match = re.search(
                r"(\d+)\s+error",
                line,
                re.IGNORECASE,
            )

            if match:
                stats["errors"] = int(match.group(1))

        return stats

    # ------------------------------------------------------------------
    # AI CONTEXT
    # ------------------------------------------------------------------

    @classmethod
    def create_ai_context(
        cls,
        log_output: str,
        repo_url: str = "",
        target_file: str = "",
    ) -> str:
        """Create compact context for the AI."""

        result = cls.process(log_output)

        return f"""
Repository: {repo_url or "unknown"}

Target File: {target_file or result["file"] or "unknown"}

Error Type:
{result["error_type"] or "unknown"}

Error Message:
{result["message"] or "unknown"}

Failed Test:
{result["test"] or "unknown"}

File:
{result["file"] or "unknown"}

Line:
{result["line"] or "unknown"}

Test Statistics:
Passed: {result["statistics"]["passed"]}
Failed: {result["statistics"]["failed"]}
Skipped: {result["statistics"]["skipped"]}
Errors: {result["statistics"]["errors"]}

Failed Tests:
{", ".join(result["failed_tests"]) or "none"}

Filtered Error Log:
{result["filtered_log"]}
""".strip()

    # ------------------------------------------------------------------
    # COMPATIBILITY METHODS
    # ------------------------------------------------------------------

    @classmethod
    def extract_key_sections(
        cls,
        log_output: str,
    ) -> dict[str, list[str] | None]:
        """Compatibility helper."""

        return {
            "errors": [
                line
                for line in log_output.splitlines()
                if cls.extract_error_type(line)
            ],
            "failures": [
                line
                for line in log_output.splitlines()
                if line.strip().upper().startswith("FAILED ")
            ],
            "passed": [
                line
                for line in log_output.splitlines()
                if "PASSED" in line.upper()
            ],
            "skipped": [
                line
                for line in log_output.splitlines()
                if "SKIPPED" in line.upper()
            ],
            "warnings": [
                line
                for line in log_output.splitlines()
                if "WARNING" in line.upper()
            ],
            "summary": [
                line
                for line in log_output.splitlines()
                if re.search(
                    r"\d+\s+(?:passed|failed|skipped|error)",
                    line,
                    re.IGNORECASE,
                )
            ],
        }

    @classmethod
    def summarize_error(
        cls,
        error_section: str,
    ) -> str:
        """Return a concise error summary."""

        result = cls.process(error_section)

        parts = []

        if result["error_type"]:
            parts.append(
                f"Error Type: {result['error_type']}"
            )

        if result["message"]:
            parts.append(
                f"Message: {result['message']}"
            )

        if result["file"]:
            parts.append(
                f"File: {result['file']}"
            )

        if result["line"]:
            parts.append(
                f"Line: {result['line']}"
            )

        if result["test"]:
            parts.append(
                f"Test: {result['test']}"
            )

        return "\n".join(parts)

    @classmethod
    def summarize_log(
        cls,
        log_output: str,
        max_lines: int = 50,
    ) -> str:
        """Return a compact filtered log."""

        filtered = cls.reduce_noise(log_output)

        lines = filtered.splitlines()

        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append(
                f"... truncated to {max_lines} lines"
            )

        return "\n".join(lines)

    @classmethod
    def extract_error_message_legacy(
        cls,
        log_output: str,
    ) -> Optional[str]:
        """Legacy alias."""

        return cls.extract_error_message(log_output)

    @classmethod
    def create_context_summary(
        cls,
        log_output: str,
        repo_url: str,
        target_file: str,
        error_message: str,
    ) -> str:
        """Backward-compatible context summary."""

        return cls.create_ai_context(
            log_output=log_output,
            repo_url=repo_url,
            target_file=target_file,
        )