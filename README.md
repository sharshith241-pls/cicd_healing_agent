# CICD Self-Healing Agent

A FastAPI application that clones a Git repository, detects a Python, Node.js,
Java, or Go project, runs its tests locally, and can ask OpenRouter to repair
multiple existing source files. It automatically uses Docker when available and
otherwise uses installed local runtimes. A successful repair is re-tested before
the optional GitHub branch, commit, push, and pull-request steps.

## Requirements

- Python 3.10 or later
- Docker Engine/Desktop (recommended for isolation; optional)
- Git
- An OpenRouter API key for AI repair
- The target project's runtime and test dependencies if Docker is unavailable
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
uvicorn main:app --host 0.0.0.0 --port 8000
```

The root-level `main.py` exports `app` for deployment platforms that scan
default FastAPI entrypoint locations. Locally, open
[http://127.0.0.1:8000/](http://127.0.0.1:8000/) for the UI,
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the API, or
`http://127.0.0.1:8000/health` for the health check. For separate static-frontend
development, `python serve.py` serves port 8000 and the API can run on port 8001.

## Supported test detection

The runner detects a root-level manifest and uses the matching command:

| Project | Detection | Test command |
|---|---|---|
| Python | `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`, or root `.py` files | `python -m pytest -q` |
| Node.js | `package.json` with a `scripts.test` entry | `npm test` |
| Java | `pom.xml`, `build.gradle`, or `build.gradle.kts` | `mvn -B test` or `gradle test --no-daemon` |
| Go | `go.mod` | `go test ./...` |

When Docker is available, tests and dependency installation run in a temporary
language-specific Docker image. Without Docker, tests run directly on the
computer using its installed Python, Node.js, Maven/Gradle, or Go tools; project
dependencies must already be installed. Direct execution is not isolated, so
only run repositories you trust. Repositories need a root manifest and a
working test command. Any UTF-8-readable source, test, and configuration file
can be included in the bounded repair context. A custom root `Dockerfile`
requires Docker. Projects requiring custom services or multiple independent
packages may need a project-specific runner.

## Multi-file repair

OpenRouter receives a bounded set of readable text files from the cloned
repository (up to 80 files and 160 KB total), plus the test output. This allows
multi-file repairs across languages when the relevant files fit the context.
It returns a JSON map of repository-relative paths to complete file contents.
The backend only applies changes to files included in that context, excludes
common secret files and build/dependency directories, and re-runs the detected
test command. If repair attempts fail, the original source context is restored.
The target-file field is optional; leaving it blank asks the agent to analyze
the repository context automatically.

## Use the local runner

The Vercel-hosted site cannot access a visitor's computer. Install Python and
Git, then run these PowerShell commands:

```powershell
git clone https://github.com/sharshith241-pls/cicd_healing_agent.git
cd cicd_healing_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your `OPENROUTER_API_KEY` to `.env`. Start Docker Desktop/Engine if you have
it, then run:

```powershell
python local_runner.py
```

Keep that process running and open the Vercel website. There is one automatic
local runner: it uses Docker when its daemon is available, or runs supported
test commands directly on this computer when Docker is unavailable. The
website's runner status shows which mode is active. The browser and companion
must be on the same computer. Allow the browser's local-network permission if
prompted. OpenRouter credentials and SQLite error memory remain on that computer.
The production site at `https://cicd-healing-agent-two.vercel.app` and
`https://cicd-healing-agent-ecef1tnnc-harshith-ss-projects-d748a198.vercel.app`
are allowed by default. If you use a different Vercel deployment URL, add its
origin to `CICD_ALLOWED_ORIGINS` in `.env`, separated from any other origins by
commas, then restart the companion.

Commits created by the pipeline use the `CICD Healing Agent` identity by
default, without changing your global Git configuration. To customize the
commit author, set `CICD_GIT_USER_NAME` and `CICD_GIT_USER_EMAIL` in `.env`.
`GITHUB_TOKEN` is still required to push the repair branch and create a pull
request. For a fine-grained GitHub token, select the target repository and
grant **Contents: Read and write** and **Pull requests: Read and write**. A
classic token needs the `repo` scope. The token's account must have write
access to the repository (and organization SSO authorization, if applicable).
After changing `GITHUB_TOKEN` in `.env`, restart `python local_runner.py`.

## Deployment notes

Start the ASGI app with:

```sh
uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Configure `OPENROUTER_API_KEY` and, when needed, `GITHUB_TOKEN` as deployment
secrets. Set `DATABASE_URL` to a persistent SQLite location or PostgreSQL
database if error memory must survive restarts.

Vercel can host the UI, but its serverless functions cannot use a visitor's
Docker daemon. Use the local companion above or deploy a separate, isolated,
access-controlled worker. Never expose an unrestricted Docker socket to a
public API: it clones and executes repositories supplied by callers.
