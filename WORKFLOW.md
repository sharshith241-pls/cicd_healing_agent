# CICD Self-Healing Agent: Workflow and Capabilities

## End-to-end workflow

1. **Select the runner.** The website can send work to a hosted API or to the
   optional local companion. The local companion uses Docker installed on the
   user's computer; it does not replace Docker or publish its socket online.
2. **Submit a repository.** The user provides a Git URL, source branch, and
   optional target file. Without a target, the agent analyzes its bounded
   repository context.
3. **Clone the repository.** The selected runner clones it into a job workspace.
   In local mode, the clone, Docker tests, SQLite database, and repair workspace
   stay on the user's computer.
4. **Detect how to test.** Root manifests identify Python, Node.js, Maven or
   Gradle Java, and Go projects. Other runtimes can provide a root `Dockerfile`;
   its image and default command are used for that job.
5. **Run initial tests in Docker.** The runner builds a temporary image and
   captures the test output and exit status. The Docker command runs inside the
   chosen runner's host.
6. **Analyze and hash the failure.** The analyzer extracts the error type,
   message, stack trace, and file when available. It normalizes the failure and
   creates a deterministic SHA-256 signature for error-memory lookup.
7. **Look for a proven repair.** SQLite/PostgreSQL memory can return a
   previously successful repair for a matching signature.
8. **Ask OpenRouter when necessary.** On a memory miss, the application gathers
   up to 80 UTF-8-readable files and 160 KB of text from the repository. Common
   secrets, binary files, dependency caches, and build outputs are excluded.
   OpenRouter can suggest a repair that changes several existing files in any
   language represented in the supplied context.
9. **Validate the candidate.** The application only applies changes to files
   included in the model context, then runs the detected/custom Docker test
   command again. Failed attempts can be retried within the configured limit.
   If repair fails, the original collected text files are restored.
10. **Deliver a passing repair.** With a GitHub token, the application can
    commit and push a repair branch and open a pull request. Without one, no
    push or PR is attempted.
11. **Show the result.** The website displays the logs, pipeline stages,
    validation result, and optional GitHub delivery details.

## Using the visitor's Docker

The website's **My Docker (this device)** option is an opt-in to a local
companion; it does not replace the ordinary Docker daemon. The visitor installs
the project, creates a local `.env`, starts Docker Desktop/Engine, and runs:

```powershell
python local_runner.py
```

The companion listens only at `127.0.0.1:8765`. While it is running, the
browser sends the repository URL to that local service. The companion clones
the project and runs its tests with the visitor's installed Docker. A browser
may ask permission to access a local-network service. The visitor's OpenRouter
key, GitHub token, error memory, and job workspace stay on their computer.

If the companion is not running, the site reports that it cannot connect. The
hosted-runner option works only if the remote API has its own Docker daemon.
Vercel serverless functions do not have access to the visitor's computer or
Docker daemon.

## Is OpenRouter enough?

No. OpenRouter is the model gateway for generating repair candidates. It does
not clone repositories, run Docker, parse or hash errors, store fix history,
push Git commits, or create pull requests. The rest of the application provides
those capabilities:

- **Git and the runner** clone repositories, choose a test strategy, and manage
  optional repair branches.
- **Docker** installs project dependencies and executes tests in a container.
- **The log processor and error analyzer** extract failure context and compute
  the deterministic SHA-256 error signature.
- **SQLite/PostgreSQL error memory** stores failures and reuses previously
  validated fixes.
- **FastAPI** coordinates the workflow and returns logs and results to the UI.
- **GitHub credentials** authorize optional branch push and pull-request
  delivery.

OpenRouter produces only a candidate. The project tests must pass before that
candidate is considered a successful repair. Passing tests do not guarantee
that every behavior is correct, so review remains important.

## Support and limitations

- Automatic test setup covers Python, Node.js packages with `scripts.test`,
  Maven/Gradle Java, and Go.
- Other text-based files can be analyzed and changed. For a different runtime,
  add a root `Dockerfile` with a default command that runs its tests.
- Source context is capped at 80 files and 160 KB. A target path is prioritized
  when the repository is larger.
- Common secret files, binary files, and dependency/build directories are
  excluded. Never put secrets in source files intended for model context.
- Local mode uses the visitor's local error-memory database; it is not
  automatically synchronized with hosted error memory.
- GitHub pushes and pull requests need a token with repository write access.
