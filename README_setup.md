# Garmin Custom MCP

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that lets an MCP-compatible AI client query and analyze data from your own Garmin Connect account. It is a work in progress; expect some analytics and setup details to change.

The server uses Garmin Connect through the community `garminconnect` Python library and stores selected activity and health history in a local SQLite database. It is designed to run on your computer, not as a public hosted service.

> **Important:** This project is unofficial and is not affiliated with or endorsed by Garmin. Use it at your own risk. Garmin may change its login flow or APIs, and some accounts may require additional authentication steps.

## What it can do

Available tools depend on the current version of the code. The current server includes tools for:

- Syncing recent Garmin activity and health data
- Retrieving recent activities and activity lap/sample details
- Querying daily health, sleep, HRV, respiration, Body Battery, training readiness, and training-load metrics when Garmin provides them
- Reviewing health trends, training summaries, recovery, and workout response
- Analyzing structured bike/run intervals and swim laps
- Evaluating or adjusting a planned workout

Some fields are unavailable for some devices, activities, or Garmin subscriptions. Results should be treated as analytical aids, not medical advice or a substitute for a qualified coach.

## Requirements

- A Garmin Connect account with activity/health data
- Python **3.12 or newer** (Python 3.12 is the version this project has been developed with)
- [`uv`](https://docs.astral.sh/uv/) for Python and dependency management
- Git, if cloning this repository
- An MCP-compatible client, such as Claude Desktop

The project dependencies are declared in `pyproject.toml`; `uv sync` installs them.

## 1. Get the project

Clone the repository (replace the URL with the URL of your fork/repository):

```bash
git clone https://github.com/YOUR-GITHUB-USERNAME/garminCustomMcp.git
cd garminCustomMcp
```

Alternatively, download the repository ZIP from GitHub and extract it.

## 2. Install Python and uv

### Windows (PowerShell)

Install `uv` using its official installer:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

Close and reopen PowerShell, then verify:

```powershell
uv --version
uv python install 3.12
uv python find 3.12
```

If you already have Python 3.12 installed, `uv python install 3.12` is usually harmless; you can skip it if desired.

### macOS / Linux

Install `uv` using the instructions at <https://docs.astral.sh/uv/getting-started/installation/>. Then install or select Python 3.12:

```bash
uv python install 3.12
uv --version
```

## 3. Install project dependencies

From the repository root—the folder containing `pyproject.toml`—run:

```bash
uv sync
```

This creates a local virtual environment (normally `.venv`) and installs the dependencies from `pyproject.toml`.

If installation fails, confirm you are in the project root and that Python 3.12 and a current version of `uv` are available.

## 4. Configure your Garmin credentials

Create a file named `.env` in the project root (next to `server.py` and `pyproject.toml`). Add your own Garmin Connect login:

```dotenv
GARMIN_EMAIL=your-garmin-email@example.com
GARMIN_PASSWORD=your-garmin-password
```

Replace the example values with your own credentials. Do not add quotes unless your password requires them, and do not commit this file to GitHub.

The code reads `GARMIN_EMAIL` and `GARMIN_PASSWORD` from `.env`. The first connection may take time or fail if Garmin rate-limits login attempts. Avoid repeatedly retrying failed logins. Garmin's authentication flow can change; multi-factor or account challenges may require additional handling that this project may not currently support.

### Security checklist

Never commit or send anyone:

- `.env` or any file containing credentials
- Garmin authentication/session tokens
- Your local SQLite database (`garmin_coach.db`), which can contain personal health and training history
- Personal activity exports or test data containing your information

Use your own credentials and database. Do not use someone else's Garmin login without permission. Before publishing a repository, inspect its full Git history as well as its current files—removing a secret from the latest version does not remove it from earlier commits.

Recommended `.gitignore` additions:

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
*.py[cod]
*.db
*.sqlite
*.sqlite3
tokens/
```

If you want to publish an example environment file, create `.env.example` containing only placeholder values—never real credentials.

## 5. Test Garmin login

From the project root, run:

```bash
uv run python -c "from garmin_client import GarminClient; client = GarminClient(); client.login(); print('Garmin login succeeded')"
```

This attempts to authenticate using the credentials in `.env`. It does not test every MCP tool. If login fails, check the credentials, internet access, Garmin account challenges, and whether Garmin is temporarily rate-limiting requests.

## 6. Connect the server to Claude Desktop

The MCP server is launched through `server.py` and communicates over standard input/output (stdio). Claude Desktop needs the absolute path to your `uv` executable and the absolute path to this project.

### Find your uv path on Windows

In PowerShell:

```powershell
(Get-Command uv).Source
```

Copy the full path returned. For example, it may resemble:

`C:\Users\YOUR_USERNAME\.local\bin\uv.exe`

### Find Claude Desktop's configuration file

On Windows, open:

`%APPDATA%\Claude\claude_desktop_config.json`

You can paste that path into File Explorer. If the file does not exist, create it and its parent folder if needed.

Add an MCP server entry. Replace both example paths with your actual paths:

```json
{
  "mcpServers": {
    "garmin-custom": {
      "command": "C:\\Users\\YOUR_USERNAME\\.local\\bin\\uv.exe",
      "args": [
        "run",
        "--directory",
        "C:\\path\\to\\garminCustomMcp",
        "python",
        "server.py"
      ]
    }
  }
}
```

If the config already contains other MCP servers, add only the `"garmin-custom"` entry inside the existing `"mcpServers"` object; do not overwrite your other entries. JSON does not allow comments or trailing commas.

Save the file completely, then quit and restart Claude Desktop. Reopening only the chat may not reload the server. Look for the Garmin tools in Claude's available tools/settings.

### macOS / Linux

The configuration structure is the same, but use the full path to `uv` and your repository, with normal Unix paths. Claude Desktop's config location varies by operating system; consult Anthropic's current MCP/Claude Desktop documentation if needed.

### Keep the server local

Do not expose this server's port or publish your credentials. This setup runs the MCP process locally and connects it to your local database.

## 7. First use and syncing

After the MCP server is connected, try these in Claude:

- “Sync my latest Garmin data.”
- “Show my health and recovery metrics for today.”
- “Summarize my activities from the last 7 days.”
- “Show my recent training load and health trends.”

The server exposes a `sync_garmin_now` tool for syncing recent data. In the current code, this syncs recent activities and today's/yesterday's health metrics. The exact coverage depends on Garmin's response and the code version.

A local SQLite database named `garmin_coach.db` is configured in `database.py`. Keep this file private; it is local personal data. Do not assume that all historical activities are loaded just because the server starts. Run a sync and verify that the expected dates and activities appear in tool results.

An optional historical sync script exists in the project (`sync.py`), but historical sync behavior may change as the project is developed. Review its current implementation before relying on it for a full import.

## 8. Troubleshooting

### Claude does not show the Garmin tools

1. Confirm the JSON configuration is valid.
2. Verify both paths in the config are absolute and correct.
3. Confirm `uv run --directory "PATH_TO_PROJECT" python server.py` works from a terminal.
4. Quit and restart Claude Desktop after changing the config.
5. Check Claude Desktop's MCP/server logs for startup errors.

### `GARMIN_EMAIL` / `GARMIN_PASSWORD` must be set

- Confirm `.env` is in the repository root, beside `server.py`.
- Confirm the variables are spelled exactly as shown.
- Ensure `.env` is a real `.env` filename, not `.env.txt` (Windows may hide file extensions).

### Garmin login fails or returns a rate-limit error

- Check your credentials and account status.
- Wait before retrying; repeated attempts may make rate limiting worse.
- Garmin's login flow may change or require additional authentication that the current implementation does not handle.

### The server starts but reports no data

- Run the `sync_garmin_now` tool.
- Confirm the activity or health metric is available in Garmin Connect for that date.
- Some fields may not be returned for every device or activity.
- Check the server logs for API, parsing, or database errors.

### Resetting your local database

The SQLite database is a local cache. Do not delete it unless you are comfortable losing the locally stored history and resyncing it. Stop the MCP server before moving or removing the database file.

## Development and tests

Install dependencies with `uv sync`. Test files are named `test_*.py`. To run the project's tests:

```bash
uv run pytest
```

Only use test results from the code version you actually ran. Some tests may rely on live Garmin data or local state; inspect a test before running it if you are unsure. Do not publish personal test data.

## Project status

This is an actively developed personal project, not a polished release. Analytics and tool behavior can change, and not every feature has been validated against every Garmin activity type. Please open an issue with a concise description, relevant sanitized logs, and reproduction steps. **Never include credentials, tokens, or private health/activity data in issues.**

## License

No license is specified in this repository yet. Unless a license is added, GitHub users may view the code, but should not assume they have permission to redistribute or reuse it. Add an appropriate license before inviting public contributions or advertising it as open source.
