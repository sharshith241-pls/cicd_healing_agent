# CICD Self-Healing Agent

A FastAPI application that clones a Git repository, detects a Python, Node.js,
Java, or Go project, runs its tests in Docker, and can ask OpenRouter to repair
multiple existing source files. A successful repair is re-tested before the
optional GitHub branch, commit, push, and pull-request steps.

## Requirements

- Python 3.10 or later
- Docker Engine/Desktop with a working daemon
- Git
- An OpenRouter API key for AI repair
- A GitHub token with repository write access for push/PR delivery

The GitHub token is optional; without it, cloning and local repair still work,
but branch push and pull-request creation are disabled.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Add your credentials to .env before running.
uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Open [http://127.0.0.1:8001/](http://127.0.0.1:8001/) for the UI,
[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) for the API, or
`http://127.0.0.1:8001/health` for the health check. For static-frontend local
development, `python serve.py` serves port 8000 and the page sends API requests
to the backend on port 8001.

## Supported test detection

The runner detects a root-level manifest and uses the matching command:

| Project | Detection | Test command |
|---|---|---|
| Python | `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`, or root `.py` files | `python -m pytest -q` |
| Node.js | `package.json` with a `scripts.test` entry | `npm test` |
| Java | `pom.xml`, `build.gradle`, or `build.gradle.kts` | `mvn -B test` or `gradle test --no-daemon` |
| Go | `go.mod` | `go test ./...` |

Tests and dependency installation run in a temporary language-specific Docker
image. Repositories need a root manifest and a working test command; projects
that require custom services, unusual toolchains, or multiple independent
packages may need a project-specific runner.

## Multi-file repair

OpenRouter receives a bounded set of readable source/configuration files from
the cloned repository (up to 80 files and 160 KB total), plus the test output.
It returns a JSON map of repository-relative paths to complete file contents.
The backend only applies changes to files included in that context, excludes
common secret files and build/dependency directories, and re-runs the detected
test command. If repair attempts fail, the original source context is restored.
The target-file field is optional; leaving it blank asks the agent to analyze
the repository context automatically.

## Deployment notes

Start the ASGI app with:

```sh
uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
```

Configure `OPENROUTER_API_KEY` and, when needed, `GITHUB_TOKEN` as deployment
secrets. Set `DATABASE_URL` to a persistent SQLite location or PostgreSQL
database if error memory must survive restarts.

The API host must also have access to a Docker daemon. Many managed Python web
services do not provide one, so the UI/API may deploy there while test and
repair jobs cannot run. For a public deployment, do not expose an unrestricted
Docker socket to this web process: it clones and executes repositories supplied
to the API. Use a separately isolated, access-controlled worker/runner for
untrusted repositories.
