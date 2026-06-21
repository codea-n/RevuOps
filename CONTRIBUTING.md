# Contributing to RevuOps

Thanks for considering a contribution. This is primarily a portfolio/learning project, but PRs and issues are welcome.

## Local Setup

1. Clone the repo and create a virtual environment:

```powershell

  python -m venv venv

  .\venv\Scripts\Activate.ps1

  pip install -r requirements.txt

```

2. Copy `.env.example` to `.env` and fill in your own API keys (Groq, Pinecone, Supabase, GitHub).

3. Run the app locally:

```powershell

  python -m uvicorn app.main:app --reload

```

## Running Tests

```powershell

python -m pytest --cov=app tests/

```

All tests must pass before a PR will be merged. CI enforces this automatically via GitHub Actions.

## Project Structure

See the architecture diagram and folder breakdown in README.md.

## Submitting a Change

1. Fork the repo, create a branch (`feature/your-change`)

2. Write tests for any new logic

3. Make sure `pytest` passes locally

4. Open a PR with a clear description of what changed and why

## Code Style

\- Follow existing patterns (e.g. `sys.executable -m tool` for subprocess calls)

\- Keep agent nodes pure functions where possible — read state, return a dict of updates

\- Mock external services (Groq, Pinecone, Supabase, GitHub API) in tests — never call them for real in CI
