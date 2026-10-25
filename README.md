# CodeStart

CodeStart is a local-first coding agent with a browser dashboard and terminal
workflow. It indexes the project you run it from, answers questions about the
codebase, proposes reviewable changes, and connects trusted MCP tools when you
need integrations beyond the local workspace.

Nothing is hosted by this project: the dashboard binds to `127.0.0.1`, source
files, chat history, API keys, indexes, and MCP connections remain on the
computer running it.

## Quick start

### Requirements

- Python **3.13**
- Node.js **18+** and npm
- A key for Gemini, OpenAI, or Anthropic — or a running local
  [Ollama](https://ollama.com/) instance

Clone the repository, then start everything with one command:

```bash
git clone <your-repository-url>
cd codestart
./run.sh
```

`run.sh` creates a local Python environment, installs CodeStart,
installs/builds the dashboard, creates `.env` from `.env.example` when needed,
and starts the dashboard at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Open **Model settings** and choose your provider, model, API keys, and fallback
chain. Add multiple keys (one per line) to recover from a quota or rate limit:
CodeStart tries additional keys for the same model first, then your fallback
models in the order shown. After saving a key, use **Refresh models** to load
the models available to that account (or local Ollama). Keys are saved only to
the local `.env` file and are never returned by the dashboard. Use `Ctrl+C` in
the terminal to stop the app.

> On macOS or Linux, make the launcher executable once after cloning if Git
> did not preserve its mode: `chmod +x run.sh`.

## What it can do

- Search and explain Python, Node.js, React, TypeScript, JavaScript, JSON,
  HTML, CSS, Vue, Svelte, Go, Rust, Java, C/C++, C#, Ruby, PHP, Swift, Kotlin,
  Bash, Dockerfiles, and other text-based project files.
- Use **Ask** for read-only answers and **Plan** to map an implementation.
- Use **Write** to stage a change in memory, inspect its diff, then apply or
  discard it yourself.
- Run local checks and ask for a diff review.
- Open **Graph** to explore local Python and JavaScript/TypeScript import links;
  click a node to preview the source file.
- Open **Git** to inspect workspace status, create/switch local branches, and
  make an explicit local commit. Git never force-switches, resets, or pushes.
- Keep local conversations and switch between saved sessions.
- Use **Execute** only after confirmation to run local commands and call MCP
  connections that you have explicitly enabled.

## MCP and tools

Open **Tools** in the dashboard header to see built-in capabilities and manage
MCP connections.

- **Filesystem** is a preset MCP server for workspace file access.
- **GitHub** is an optional preset. Set `GITHUB_TOKEN` in local `.env` first,
  then connect it in Tools.
- **Custom stdio MCP** lets you add a trusted command and arguments, such as
  an MCP package run by `npx`. Arguments are entered one per line. Optional
  `KEY=value` environment variables stay in the local MCP configuration.

MCP configuration is stored in `.claude_code/mcp_servers.json`, which is
ignored by Git. API-key values are never displayed after saving. Custom MCP
servers run commands on the host computer, so only connect sources you trust.
MCP tools are available in **Execute** mode; the normal Ask, Plan, and staged
Write modes preserve the safe local workflow.

GitHub is supported through the optional **GitHub MCP** connection in Tools.
Connect it with a local `GITHUB_TOKEN`, then use Execute for an explicitly
requested GitHub action such as creating an issue or pull request. CodeStart
does not push, create remotes, or modify GitHub unless you explicitly ask it to.

For terminal-only usage, the earlier opt-in environment variables still work:

```bash
CLAUDE_CODE_ENABLE_MCP=true poetry run codestart
CLAUDE_CODE_ENABLE_MCP=true CLAUDE_CODE_ENABLE_GITHUB_MCP=true poetry run codestart
```

## Terminal usage

If you prefer Poetry instead of the launcher:

```bash
poetry install --with dev
cp .env.example .env
poetry run codestart
```

Useful commands:

```text
/ask Where is session state stored?
/plan Add authentication to the API.
/write Add authentication and update tests.
/diff
/apply
/test
/review
/files [query]
/open <path>
/sessions
/help
```

Start the browser UI with `poetry run codestart --dashboard`. The dashboard
will use the current directory as its workspace, so run it from the project
you want to inspect.

## Project configuration

`config.yaml` controls the model, embeddings, local FAISS index, local session
database, and skill directory. The default FAISS index is incremental: after
the first run it only re-embeds changed source files. Pinecone is optional.

Generated local state is intentionally ignored by Git:

- `.env` — provider and integration secrets
- `.faiss/`, `.chromadb/` — local indexes
- `.memory/` — conversation database
- `.claude_code/mcp_servers.json` — connected MCP definitions
- `.venv/`, `dashboard/node_modules/`, and `dashboard/dist/`

## Development

```bash
poetry install --with dev
cd dashboard && npm ci && npm run build && cd ..
poetry run pytest
poetry run ruff check claude_code tests
poetry run pyright
```

## Contributing

CodeStart is designed to be approachable for first-time contributors. Start
with [CONTRIBUTING.md](CONTRIBUTING.md): it explains the development setup,
branch and pull-request expectations, and how to select a beginner-friendly
issue. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and report security
issues privately using [SECURITY.md](SECURITY.md).

Useful contribution ideas are tracked in the `good first issue`,
`help wanted`, `provider`, and `integration` labels. A healthy contribution
keeps the local-first promise: no API key, workspace content, or remote tool is
used without a deliberate user action.

## GitHub release checklist

This repository is ready to publish after you create a GitHub repository:

```bash
git init
git add .
git commit -m "Initial release"
git branch -M main
git remote add origin https://github.com/<owner>/<repository>.git
git push -u origin main
```

Do not commit `.env`, indexes, session data, or local MCP configuration.
