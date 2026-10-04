# Setup (Windows)

Prerequisites: Python 3.12, Git, GitHub CLI. `uv` is installed with `pip install --user uv` and run
as `python -m uv` (or add `%APPDATA%\Python\Python312\Scripts` to PATH to use `uv` directly).

## 1. Keys (`.env` at the repo root, gitignored)

```
AIRLABS_API_KEY=...        # airlabs.co, free plan
SERPAPI_KEY=...            # serpapi.com, free plan
ANTHROPIC_API_KEY=         # optional; leave empty to use your Claude Code login
TRAVEL_AGENT_MODEL=        # optional; sonnet | opus | haiku
TRAVEL_WEB_KEY_ONLY=       # optional; 1 = web UI ignores the Claude login, visitors enter a key
```

No Claude Code login and no key in `.env`? The web UI asks for an Anthropic API key in the browser
instead (see [ui.md](ui.md#claude-access-login-or-api-key)).

```
```

## 2. MCP server

```powershell
cd "D:\My Projects\01-travel-assistant\mcp-server"
python -m uv sync --extra dev
python -m uv run pytest
python -m uv run python scripts/smoke_live.py      # 2 real API calls
```

## 3. Policy knowledge base

Save the 6 IndiGo and Air India pages listed in `rag/sources.yaml` from a browser (Ctrl+S,
"Webpage, HTML only") into `rag/manual/` using the filenames given there. Then:

```powershell
python -m uv run travel-rag ingest     # first run downloads the embedding model (~70 MB)
python -m uv run travel-rag sources
```

## 4. Claude Desktop

In `claude_desktop_config.json`:

```json
{ "mcpServers": { "travel-assistant": {
    "command": "uv",
    "args": ["--directory", "D:\\My Projects\\01-travel-assistant\\mcp-server", "run", "travel-mcp"] } } }
```

If `uv` isn't on PATH, use `"command": "D:\\My Projects\\01-travel-assistant\\mcp-server\\.venv\\Scripts\\travel-mcp.exe"` with no args.
Fully quit Claude Desktop from the tray and reopen it.

## 5. Agent, UI and evals

```powershell
cd ..\agent
python -m uv sync --extra dev
python -m uv run pytest
python -m uv run travel-agent ask "Cheapest nonstop HYD to MAA next Friday?" -v
python -m uv run travel-eval --model haiku

cd ..\ui; npm install; npm run build
cd ..\agent; python -m uv run travel-agent web --open   # chat UI at http://127.0.0.1:8765
```
