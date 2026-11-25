# Deployment (Docker-capable host)

## Choose a Docker-capable host

The application runs as a FastAPI web service, but its test runner also calls
the Docker CLI and requires a working Docker daemon. Deploy it on a persistent
Linux VM or another host that provides Docker to the application. Vercel
Functions and other serverless Python runtimes generally do not provide that
daemon, so they can serve neither the complete test-and-repair workflow nor
its Docker-based tests.

Do not expose an unrestricted Docker socket to a public application container.
The API clones and executes repositories supplied by callers. For public or
multi-user deployment, put test execution in a separate, isolated, access-
controlled worker and authenticate requests to the web API.

## Configure and start

1. Deploy this repository and install Python, Git, and Docker Engine.
2. Install application dependencies with `pip install -r requirements.txt`.
3. Configure these environment variables in the host's secret manager:
   - `OPENROUTER_API_KEY` — required for AI-generated repairs.
   - `OPENROUTER_MODEL` — optional; defaults to `openrouter/free`.
   - `GITHUB_TOKEN` — optional; needed to push repair branches and create PRs.
   - `DATABASE_URL` — optional; defaults to a SQLite file under `workspace/`.
     Use persistent storage or PostgreSQL if error memory must survive restarts.
4. Start the ASGI service:

   ```sh
   uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
   ```

5. Configure the platform health check to `GET /health`. The UI is at `/` and
   the interactive API documentation is at `/docs`.

The GitHub token must have permission to create branches, push commits, and
open pull requests in repositories selected by the operator. Keep secrets out
of source control and never put them in the frontend.

## Vercel frontend with the visitor's Docker

Vercel Functions cannot connect to a visitor's Docker daemon. Deploy the UI/API
normally, then let users select **My Docker (this device)** in the web UI. The
user must clone/download the project, configure their own `.env`, start Docker,
and launch `python local_runner.py`. This loopback-only companion processes the
repository and retains its API key, error-memory database, and workspace
locally. The production origin `https://cicd-healing-agent-two.vercel.app` is
allowed by default. If the deployment URL changes, allow that exact origin
through `CICD_ALLOWED_ORIGINS` in the companion's local `.env` and restart it.
