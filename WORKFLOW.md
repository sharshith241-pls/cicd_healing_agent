# CICD Self-Healing Agent: Workflow and Capabilities

## End-to-end workflow

1. **Connect to the local runner.** The website sends work to the companion
   running on the user's computer. There is no hosted-runner selector.
2. **Submit a repository.** The user provides a Git URL, source branch, and
   optional target file. Without a target, the agent analyzes its bounded
   repository context.
3. **Clone the repository.** The local companion clones it into a job workspace.
   The clone, tests, SQLite database, and repair workspace stay on the user's
   computer.
4. **Detect how to test.** Root manifests identify Python, Node.js, Maven or
   Gradle Java, and Go projects. Other runtimes can provide a root `Dockerfile`;
   its image and default command are used for that job.
5. **Run initial tests locally.** If Docker is available, the runner builds a
   temporary image and captures the test output and exit status. Otherwise it
   runs the language's test command using locally installed tools and
   dependencies. Direct execution is not isolated; only run trusted repositories.
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
   included in the model context, then runs the detected test command again
   using the same automatic execution mode. Failed attempts can be retried
   within the configured limit.
   If repair fails, the original collected text files are restored.
10. **Deliver a passing repair.** With a GitHub token, the application can
    commit and push a repair branch and open a pull request. Without one, no
    push or PR is attempted.
11. **Show the result.** The website displays the logs, pipeline stages,
    validation result, and optional GitHub delivery details.

## Using the visitor's local runner

The visitor installs the project, creates a local `.env`, optionally starts
Docker Desktop/Engine, and runs:

```powershell
python local_runner.py
```

The companion listens only at `127.0.0.1:8765`. While it is running, the
browser sends the repository URL to that local service. The companion clones
the project and automatically uses Docker if available, otherwise running
supported test commands directly on the computer. Native execution is not
isolated and should be used only with trusted repositories. A browser may ask
permission to access a local-network service. The visitor's OpenRouter key,
GitHub token, error memory, and job workspace stay on their computer.

If the companion is not running, the site reports that it cannot connect.
Vercel serverless functions do not have access to the visitor's computer.

## Is OpenRouter enough?

No. OpenRouter is the model gateway for generating repair candidates. It does
not clone repositories, run Docker, parse or hash errors, store fix history,
push Git commits, or create pull requests. The rest of the application provides
those capabilities:

- **Git and the runner** clone repositories, choose a test strategy, and manage
  optional repair branches.
- **The local test runner** uses Docker for isolation when available; otherwise
  it runs test commands with installed local runtimes and dependencies.
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
  add a root `Dockerfile` with a default command that runs its tests. Custom
  Dockerfiles require Docker and cannot use the native fallback.
- Source context is capped at 80 files and 160 KB. A target path is prioritized
  when the repository is larger.
- Common secret files, binary files, and dependency/build directories are
  excluded. Never put secrets in source files intended for model context.
- Local mode uses the visitor's local error-memory database; it is not
  automatically synchronized with hosted error memory.
- GitHub pushes and pull requests need a token with repository write access.
