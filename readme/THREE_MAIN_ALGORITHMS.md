# Three Main Algorithms Used in the CICD Self-Healing System

## 1. Error Memory and Multi-Level Error Matching Algorithm

### Purpose

The error-memory algorithm identifies whether a newly detected CI/CD failure has
already been observed and whether a previously validated fix can be reused. This
reduces repeated AI calls and allows the system to learn from successful repairs.

### Input

- Error type
- Error message
- Stack trace
- Repository URL
- Target source file

### Processing

First, the error message is normalized. Runtime-dependent values are replaced so
that equivalent failures can be compared consistently:

- Memory addresses are replaced with `0x...`.
- Dates are replaced with `DATE`.
- Line numbers are replaced with `line X`.
- Text is converted to lowercase.

A deterministic error fingerprint is then generated:

\[
H(e) = SHA256(\operatorname{lowercase}(t + ":" + m))
\]

where \(t\) is the error type and \(m\) is the error message.

The system compares errors using the following priority order.

#### Level 1: Normalized exact matching

Two errors match when:

\[
N(m_1) = N(m_2)
\]

and:

\[
t_1 = t_2
\]

An exact match receives a confidence score of `1.0`.

#### Level 2: Fuzzy message matching

If exact matching fails, normalized messages are compared using
`SequenceMatcher`. The match is accepted when:

\[
S(m_1,m_2) \geq 0.75
\]

The error types must also be equal. A fuzzy match receives a confidence score of
`0.85`.

#### Level 3: Stack-trace pattern matching

If message matching fails, the system extracts file names and function names
from both stack traces. File similarity is calculated using Jaccard similarity:

\[
J_f = \frac{|F_1 \cap F_2|}{|F_1 \cup F_2|}
\]

Function similarity is calculated as:

\[
J_g = \frac{|G_1 \cap G_2|}{|G_1 \cup G_2|}
\]

The final stack-trace score is:

\[
P = \frac{J_f + J_g}{2}
\]

A pattern match is accepted when:

\[
P \geq 0.60
\]

The pattern score is used as the confidence value.

### Fix retrieval decision

After the error is identified, the database is searched using the error
fingerprint. A stored fix is reused only when its historical success rate is at
least `0.5`:

\[
\text{ReuseFix} =
\begin{cases}
\text{true}, & \text{if success rate} \geq 0.5 \\
\text{false}, & \text{otherwise}
\end{cases}
\]

The cache confidence is capped at `0.95`:

\[
C_{\text{cache}} = \min(\text{success rate}, 0.95)
\]

### Pseudocode

```text
function RESOLVE_ERROR(error):
    normalized_message = NORMALIZE(error.message)
    error_hash = SHA256(error.type + ":" + error.message)

    record = DATABASE_LOOKUP(error_hash)

    if record exists and record.fix.success_rate >= 0.5:
        return record.fix, "cache"

    for stored_error in DATABASE_CANDIDATES:
        if NORMALIZED_EXACT_MATCH(error, stored_error):
            return stored_error.fix, "exact"

        if FUZZY_MATCH(error, stored_error, threshold=0.75):
            return stored_error.fix, "fuzzy"

        if STACK_PATTERN_MATCH(error, stored_error, threshold=0.60):
            return stored_error.fix, "pattern"

    return NO_CACHED_FIX
```

### Research significance

This algorithm combines deterministic fingerprinting, string similarity, and
structural stack-trace comparison. Its main benefit is experience reuse:
failures that have already been repaired successfully can be resolved without
generating a new AI patch.

---

## 2. CI/CD Log Processing and Structured Error Extraction Algorithm

### Purpose

CI/CD output contains useful failure information mixed with platform details,
pytest summaries, separators, and empty lines. The log-processing algorithm
converts this unstructured output into a compact structured error record.

### Input

Raw Docker and pytest output.

### Processing stages

1. Remove predefined noise patterns using regular expressions.
2. Extract the error or exception type.
3. Extract the error message.
4. Extract the source file and line number.
5. Extract the failed test name.
6. Extract all failed test identifiers.
7. Count passed, failed, skipped, and errored tests.
8. Preserve a filtered log for later analysis and AI context.

The structured result is:

\[
E = \{t, m, f, n, q, F, \sigma, L_r, L_f\}
\]

where:

- \(t\) = error type
- \(m\) = error message
- \(f\) = file
- \(n\) = line number
- \(q\) = primary failed test
- \(F\) = list of failed tests
- \(\sigma\) = test statistics
- \(L_r\) = raw log size
- \(L_f\) = filtered log size

### Pseudocode

```text
function PROCESS_LOG(raw_log):
    if raw_log is empty:
        return empty_error_record

    filtered_log = []

    for line in raw_log:
        if line matches a noise pattern:
            continue
        if line is empty:
            continue
        append line to filtered_log

    error_type = EXTRACT_ERROR_TYPE(raw_log)
    message = EXTRACT_ERROR_MESSAGE(raw_log)
    location = EXTRACT_FILE_AND_LINE(raw_log)
    test_name = EXTRACT_TEST_NAME(raw_log)
    failed_tests = EXTRACT_FAILED_TESTS(raw_log)
    statistics = EXTRACT_TEST_STATISTICS(raw_log)

    success = (
        statistics.failed == 0
        and statistics.errors == 0
        and error_type is null
    )

    return {
        error_type,
        message,
        location,
        test_name,
        failed_tests,
        statistics,
        filtered_log,
        success
    }
```

### Log-reduction metric

The reduction ratio can be measured as:

\[
R = 1 - \frac{L_f}{L_r}
\]

where \(L_r\) is the raw log size and \(L_f\) is the filtered log size.

### Research significance

This algorithm transforms noisy execution output into a consistent diagnostic
representation. The structured representation improves database lookup,
similarity matching, AI prompt construction, and result reporting.

---

## 3. AI-Assisted Repair and Test-Validation Algorithm

### Purpose

When the error memory does not contain a reliable repair, the system generates a
candidate source-code fix using the original file and structured test failure
context. The candidate is accepted only after validation.

### Input

- Original source code
- Target file
- Structured error information
- Filtered test output
- Repository path
- Maximum repair attempts

### Processing

1. Verify that the repository and target file exist.
2. Check the error-memory cache.
3. Store a new error record if no matching error exists.
4. Send the source code and failure context to the AI repair model.
5. Receive a candidate repair.
6. Apply the candidate repair.
7. Re-run the repository tests.
8. Store the repair if validation succeeds.
9. If validation fails, perform another repair attempt when permitted.

### Pseudocode

```text
function SELF_HEAL(repository, target_file, error, max_attempts):
    cached_fix = ERROR_MEMORY_LOOKUP(error)

    if cached_fix is reliable:
        APPLY(cached_fix)
        if RUN_TESTS(repository) == PASS:
            return cached_fix, "cache"

    for attempt from 1 to max_attempts:
        candidate = AI_GENERATE(
            source_code=READ(target_file),
            error=error,
            test_output=error.filtered_log
        )

        if candidate is empty:
            continue

        APPLY(candidate, target_file)
        validation_result = RUN_TESTS(repository)

        if validation_result == PASS:
            STORE_SUCCESSFUL_FIX(error, candidate)
            return candidate, "ai"

        RESTORE_OR_PREPARE_NEXT_ATTEMPT()

    return FAILURE
```

### Decision model

The repair pipeline follows:

\[
\text{Detect} \rightarrow \text{Retrieve or Generate}
\rightarrow \text{Apply} \rightarrow \text{Test}
\rightarrow \text{Store or Retry}
\]

The AI-generated repair is assigned a heuristic confidence of `0.80` in the
current implementation. This value represents a prioritization score, not a
statistically calibrated probability.

### Research significance

The algorithm uses AI for candidate patch generation but retains deterministic
control over repository validation and learning. This hybrid design prevents an
AI response from being treated as successful unless the repaired repository
passes its test suite.

---

## Summary of the Three Algorithms

| Algorithm | Main technique | Main output |
|---|---|---|
| Error memory and matching | SHA-256 fingerprinting, exact matching, fuzzy matching, Jaccard stack-trace similarity | Previously validated fix or match confidence |
| Log processing and extraction | Regular expressions, noise filtering, structured parsing | Structured error record |
| AI repair and validation | AI patch generation, iterative retry, automated test validation | Validated repair or failure result |

## Main Contribution

The framework combines deterministic error analysis with AI-assisted repair. The
first algorithm provides experience reuse, the second converts unstructured
execution logs into machine-readable diagnostic data, and the third generates
and validates repairs. Together, these algorithms form a closed-loop
self-healing CI/CD process.
