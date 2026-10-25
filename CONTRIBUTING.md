# Contributing to CodeStart

Thanks for improving CodeStart. The project is intentionally local-first:
contributions must not send source code, API keys, or telemetry anywhere unless
the user has explicitly configured and requested it.

## First contribution

1. Fork the repository and create a branch from `main`.
2. Run `./run.sh` once, then open `http://127.0.0.1:8000`.
3. Pick an issue labeled `good first issue` or open an issue before starting a
   larger change.
4. Keep a change focused and add or update tests for behavior changes.
5. Run the checks below before opening a pull request.

```bash
poetry run pytest
poetry run ruff check claude_code tests
poetry run pyright
cd dashboard && npm run build
```

## Pull requests

- Explain the user problem, approach, and validation in the PR description.
- Include screenshots for dashboard UI changes.
- Do not commit `.env`, provider keys, local indexes, chat history, or MCP
  connection files.
- Preserve the staged-change workflow: generated code must be reviewable before
  it writes to the workspace.
- Use clear, inclusive language and keep new dependencies justified.

## Areas we welcome

- More provider adapters and robust key/fallback handling
- MCP presets and integration documentation
- Accessibility, responsive design, and onboarding improvements
- Indexer support for additional languages and project structures
- Tests, examples, and beginner-friendly documentation

By contributing, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
