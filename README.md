# Code Assistant

Code Assistant is a local-first coding agent with a browser dashboard and a
terminal workflow. It indexes the project you run it from, answers questions
about the codebase, proposes reviewable changes, and lets you connect trusted
MCP tools when you need integrations beyond the local workspace.

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
cd code-assistant
./run.sh
```

`run.sh` creates a local Python environment, installs the Python package,
installs/builds the dashboard, creates `.env` from `.env.example` when needed,
and starts the dashboard at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Open **Model settings** and choose your provider, model, API key, and optional
fallback. After saving a key, use **Refresh models** to load the models available
to that account (or local Ollama). Keys are saved only to the local `.env` file
and are never returned by the dashboard. Use `Ctrl+C` in the terminal to stop
the app.

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

For terminal-only usage, the earlier opt-in environment variables still work:

```bash
CLAUDE_CODE_ENABLE_MCP=true poetry run claude_code
CLAUDE_CODE_ENABLE_MCP=true CLAUDE_CODE_ENABLE_GITHUB_MCP=true poetry run claude_code
```

## Terminal usage

If you prefer Poetry instead of the launcher:

```bash
poetry install --with dev
cp .env.example .env
poetry run claude_code
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

Start the browser UI with `poetry run claude_code --dashboard`. The dashboard
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
