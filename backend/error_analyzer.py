"""Error Analyzer Module - Extract, normalize, and match errors using multiple strategies."""

import hashlib
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ErrorInfo:
    """Container for error information."""

    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    repo_url: Optional[str] = None
    file_path: Optional[str] = None
    error_hash: Optional[str] = None


class ErrorAnalyzer:
    """Analyze and match errors using multiple strategies."""

    # Stack trace pattern for extracting key information
    STACK_TRACE_PATTERN = re.compile(
        r"(?P<file>\S+\.py):(?P<line>\d+) in (?P<func>\w+)|(?P<error_line>.*Error.*)",
        re.MULTILINE,
    )

    @staticmethod
    def extract_error_hash(error_message: str, error_type: str) -> str:
        """Generate deterministic hash from error."""
        combined = f"{error_type}:{error_message}".lower().strip()
        return hashlib.sha256(combined.encode()).hexdigest()

    @staticmethod
    def normalize_error_message(message: str) -> str:
        """Normalize error message for comparison."""
        # Remove memory addresses, timestamps, variable values
        normalized = re.sub(r"0x[0-9a-f]+", "0x...", message, flags=re.IGNORECASE)
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", normalized)
        normalized = re.sub(r"line \d+", "line X", normalized, flags=re.IGNORECASE)
        normalized = normalized.lower().strip()
        return normalized

    @staticmethod
    def extract_stack_trace_features(stack_trace: str) -> dict:
        """Extract key features from stack trace."""
        features = {
            "files": [],
            "functions": [],
            "error_lines": [],
            "unique_files": set(),
        }

        for match in ErrorAnalyzer.STACK_TRACE_PATTERN.finditer(stack_trace):
            if match.group("file"):
                features["files"].append(match.group("file"))
                features["unique_files"].add(match.group("file"))
            if match.group("func"):
                features["functions"].append(match.group("func"))
            if match.group("error_line"):
                features["error_lines"].append(match.group("error_line"))

        return features

    @staticmethod
    def exact_match(error_message_1: str, error_message_2: str) -> bool:
        """Check if errors match exactly."""
        norm_1 = ErrorAnalyzer.normalize_error_message(error_message_1)
        norm_2 = ErrorAnalyzer.normalize_error_message(error_message_2)
        return norm_1 == norm_2

    @staticmethod
    def fuzzy_match(error_message_1: str, error_message_2: str, threshold: float = 0.75) -> bool:
        """Fuzzy match using SequenceMatcher."""
        norm_1 = ErrorAnalyzer.normalize_error_message(error_message_1)
        norm_2 = ErrorAnalyzer.normalize_error_message(error_message_2)

        similarity = SequenceMatcher(None, norm_1, norm_2).ratio()
        return similarity >= threshold

    @staticmethod
    def stack_trace_pattern_match(
        stack_trace_1: Optional[str],
        stack_trace_2: Optional[str],
        threshold: float = 0.6,
    ) -> tuple[bool, float]:
        """Match stack traces by comparing patterns."""
        if not stack_trace_1 or not stack_trace_2:
            return False, 0.0

        features_1 = ErrorAnalyzer.extract_stack_trace_features(stack_trace_1)
        features_2 = ErrorAnalyzer.extract_stack_trace_features(stack_trace_2)

        # Compare unique files
        if features_1["unique_files"] and features_2["unique_files"]:
            intersection = len(features_1["unique_files"] & features_2["unique_files"])
            union = len(features_1["unique_files"] | features_2["unique_files"])
            jaccard_similarity = intersection / union if union > 0 else 0.0
        else:
            jaccard_similarity = 0.0

        # Compare function names
        if features_1["functions"] and features_2["functions"]:
            func_similarity = len(set(features_1["functions"]) & set(features_2["functions"])) / max(
                len(set(features_1["functions"]) | set(features_2["functions"])), 1
            )
        else:
            func_similarity = 0.0

        combined_score = (jaccard_similarity + func_similarity) / 2
        return combined_score >= threshold, combined_score

    @staticmethod
    def parse_error_from_log(log_output: str) -> Optional[ErrorInfo]:
        """Extract error information from log output."""
        lines = log_output.split("\n")

        error_type = None
        error_message = None
        stack_trace = []
        in_traceback = False

        for i, line in enumerate(lines):
            # Look for error type and message (last non-empty line before stack)
            if line.strip() and ("Error" in line or "Exception" in line):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    error_type = parts[0].strip()
                    error_message = parts[1].strip()

            # Detect traceback
            if "Traceback" in line:
                in_traceback = True
            if in_traceback:
                stack_trace.append(line)

        if error_type and error_message:
            error_hash = ErrorAnalyzer.extract_error_hash(error_message, error_type)
            return ErrorInfo(
                error_type=error_type,
                error_message=error_message,
                stack_trace="\n".join(stack_trace) if stack_trace else None,
                error_hash=error_hash,
            )

        return None

    @staticmethod
    def compare_errors(error_1: dict, error_2: dict) -> dict:
        """Compare two errors using all strategies.
        
        Returns dict with:
            - exact_match: bool
            - fuzzy_match: bool
            - pattern_match: bool + score
            - best_match_type: string
            - confidence: float (0-1)
        """
        msg_1 = error_1.get("error_message", "")
        msg_2 = error_2.get("error_message", "")
        type_1 = error_1.get("error_type", "")
        type_2 = error_2.get("error_type", "")
        stack_1 = error_1.get("stack_trace")
        stack_2 = error_2.get("stack_trace")

        # Strategy 1: Exact match
        exact = (
            ErrorAnalyzer.exact_match(msg_1, msg_2) and type_1 == type_2
        )

        # Strategy 2: Fuzzy match
        fuzzy = (
            ErrorAnalyzer.fuzzy_match(msg_1, msg_2, threshold=0.75)
            and type_1 == type_2
        )

        # Strategy 3: Stack trace pattern
        pattern_match, pattern_score = ErrorAnalyzer.stack_trace_pattern_match(
            stack_1, stack_2, threshold=0.6
        )

        # Determine best match
        if exact:
            best_match = "exact"
            confidence = 1.0
        elif fuzzy:
            best_match = "fuzzy"
            confidence = 0.85
        elif pattern_match:
            best_match = "pattern"
            confidence = pattern_score
        else:
            best_match = "none"
            confidence = 0.0

        return {
            "exact_match": exact,
            "fuzzy_match": fuzzy,
            "pattern_match": pattern_match,
            "pattern_score": pattern_score,
            "best_match_type": best_match,
            "confidence": confidence,
        }
