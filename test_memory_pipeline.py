from backend.docker_runner import DockerRunner
from backend.log_processor import LogProcessor
from backend.error_database import ErrorDatabase
import hashlib

print("--- RUNNING PIPELINE ---")

# 1. Run repository inside Docker
result = DockerRunner("./workspace/docker_test").run()

# 2. Process the Docker logs
parsed = LogProcessor.process(result["logs"])

# 3. Create a stable error signature
signature = (
    f"{parsed['error_type']}|"
    f"{parsed['message']}|"
    f"{parsed['file']}"
)

error_hash = hashlib.sha256(
    signature.encode("utf-8")
).hexdigest()

# 4. Search failure memory
db = ErrorDatabase(
    "sqlite:///./workspace/cicd_errors.db"
)

error = db.get_error_by_hash(error_hash)

# 5. Search for a known successful fix
fix = (
    db.get_fix_for_error(error["id"])
    if error
    else None
)

print()
print("--- PIPELINE RESULT ---")
print("Docker success:", result["success"])
print("Error:", parsed["error_type"])
print("Message:", parsed["message"])
print("File:", parsed["file"])
print("Line:", parsed["line"])
print("Test:", parsed["test"])
print("Known error:", error is not None)
print("Known fix:", fix is not None)

if fix:
    print("Fix success rate:", fix["success_rate"])
    print("Fix description:", fix["fix_description"])

db.close()
