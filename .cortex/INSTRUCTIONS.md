@c# Azure DevOps MCP Server — Developer Instructions

> **Purpose**: Self-reference guide for AI assistants and developers working on this codebase.

## Project Overview

An MCP (Model Context Protocol) server that exposes **41 Azure DevOps REST API tools** to AI assistants via stdio. It covers pipelines, Git repositories, pull requests, releases, boards, work items, test management, and wikis.

- **Language**: Python 3.10+
- **Package manager**: pip or [uv](https://docs.astral.sh/uv/)
- **Build system**: Hatchling via `pyproject.toml`
- **Transport**: MCP stdio (no HTTP server)
- **PyPI**: `pip install azure-devops-mcp`

---

## Architecture

```
azure-devops-mcp/
├── src/azure_devops_mcp/          ← pip-installable package (src layout)
│   ├── __init__.py                ← Package marker + __version__
│   ├── __main__.py                ← CLI entry point (azure-devops-mcp command)
│   ├── server.py                  ← MCP server — registers all 41 tools via @mcp.tool()
│   ├── auth.py                    ← Multi-auth: PAT, Client Credentials, Managed Identity, Device Code
│   └── clients/
│       ├── __init__.py            ← Empty package marker
│       ├── pipelines.py           ← Pipeline + build artifact API calls
│       ├── releases.py            ← Classic releases + approvals (vsrm.dev.azure.com)
│       ├── git.py                 ← Repos, branches, commits, PRs, comments, diffs
│       ├── boards.py              ← Boards, work items, WIQL, saved queries, comments
│       ├── tests.py               ← Test runs, results, code coverage
│       └── wiki.py                ← Wiki pages (list/get/create-update)
├── tests/
│   ├── test_auth.py               ← Auth detection + header generation tests (13 tests)
│   ├── test_server.py             ← Project resolution + tool registration tests (8 tests)
│   └── test_clients.py            ← Response shaping + URL construction tests (21 tests)
├── .github/workflows/ci.yml      ← CI: runs tests on push/PR to main (Python 3.10-3.13)
├── .env.example                   ← Env var template (all 4 auth methods)
├── pyproject.toml                 ← Dependencies, build config, CLI entry point
└── README.md                      ← User-facing docs with Quick Start
```

### Data Flow

```
AI Client (Copilot/Claude/Cursor)
  ↕ MCP stdio
__main__.py → server.py  (tool dispatcher)
  → lazy-imports clients/<module>.py
      → auth.py  (auto-detects auth method, acquires token)
      → httpx REST call → Azure DevOps API (api-version=7.1)
```

---

## Key Design Patterns

### 1. Lazy Imports in server.py

All client modules are imported **inside the tool functions**, not at the top of `server.py`:

```python
@mcp.tool()
def list_pipelines(project: str = "") -> list[dict]:
    from azure_devops_mcp.clients.pipelines import list_pipelines as _list_pipelines  # lazy
    return _list_pipelines(_resolve_project(project))
```

**Why**: Avoids import-time auth failures and speeds up MCP tool discovery.

### 2. `_resolve_project()` Pattern

Every tool accepts an optional `project` param. `_resolve_project()` falls back to the `AZURE_DEVOPS_PROJECT` env var:

```python
def _resolve_project(project: str | None) -> str:
    p = project or DEFAULT_PROJECT
    if not p:
        raise ValueError("Project name is required...")
    return p
```

### 3. Each Client Has Its Own `_api()` Helper

Every `clients/*.py` file defines its own `_api()` function that:
- Acquires auth header via `auth.get_auth_header()` (auto-detects method)
- Sets `api-version=7.1`
- Implements **retry with exponential backoff** for `429` and `5xx` (3 retries)
- Uses `httpx.Client` for requests

### 4. Response Shaping

All client functions return clean `dict`/`list[dict]` — extracting only relevant fields from raw Azure DevOps API responses. They never return raw API payloads.

### 5. Identity Formatting

Each client has a `_format_identity()` helper that extracts `displayName` or `uniqueName` from Azure identity objects. This is duplicated per module (not shared).

---

## Authentication

The server supports **4 auth methods**, auto-detected from env vars (priority order):

| Priority | Method | Triggered By | Auth Type |
|----------|--------|-------------|-----------|
| 1 | **PAT** | `AZURE_DEVOPS_PAT` | Basic auth (`:PAT` base64) |
| 2 | **Client Credentials** | `AZURE_CLIENT_ID` + `AZURE_CLIENT_SECRET` + `AZURE_TENANT_ID` | Bearer (MSAL ConfidentialClientApplication) |
| 3 | **Managed Identity** | `AZURE_USE_MANAGED_IDENTITY=true` | Bearer (azure-identity SDK) |
| 4 | **Device Code** | *(default fallback)* | Bearer (MSAL device code flow) |

Detection logic is in `auth._detect_auth_method()`. The public API is `get_auth_header()` — all clients call this, and it dispatches to the correct method.

- **PAT**: Returns `Basic` header. No token acquisition needed.
- **Client Credentials**: Uses `msal.ConfidentialClientApplication` with cached tokens.
- **Managed Identity**: Requires optional dep `azure-identity` (`pip install azure-devops-mcp[managed-identity]`).
- **Device Code**: Uses Azure DevOps first-party client ID (`872cd9fa-...`). No app registration needed. Token cached at `~/.azure-devops-mcp/token_cache.json`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_DEVOPS_ORG_URL` | **Yes** | — | `https://dev.azure.com/{org}` |
| `AZURE_DEVOPS_PROJECT` | No | `""` | Default project, overridable per tool call |
| `AZURE_DEVOPS_PAT` | No | — | PAT auth |
| `AZURE_CLIENT_ID` | No | — | Service principal or user-assigned MI client ID |
| `AZURE_CLIENT_SECRET` | No | — | Service principal secret |
| `AZURE_TENANT_ID` | No | `organizations` | Azure AD tenant |
| `AZURE_USE_MANAGED_IDENTITY` | No | — | Set `true` for managed identity |

Loaded from `.env` via `python-dotenv` or passed via MCP client `env` config.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `mcp[cli]>=1.0.0` | MCP server framework (FastMCP) |
| `msal>=1.20.0` | Microsoft auth library (device code + client credentials) |
| `python-dotenv>=1.0.0` | `.env` file loading |
| `httpx>=0.27.0` | HTTP client for REST API calls |
| `azure-identity>=1.15.0` | *(optional)* Managed Identity support |
| `pytest>=7.0.0` | *(dev)* Test runner |
| `pytest-cov>=4.0.0` | *(dev)* Coverage reporting |

---

## Running

```bash
# Install from PyPI
pip install azure-devops-mcp

# Run the server (as CLI command)
azure-devops-mcp

# Or run as module
python -m azure_devops_mcp

# Dev inspector (interactive tool testing)
PYTHONPATH=src python -m mcp dev src/azure_devops_mcp/server.py

# Install from source (development)
pip install -e ".[dev]"
```

---

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all 42 tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=azure_devops_mcp --cov-report=term-missing
```

### CI Pipeline (`.github/workflows/ci.yml`)

- Triggers on **push to `main`** and **PRs to `main`**
- Tests across **Python 3.10, 3.11, 3.12, 3.13**
- Runs pytest with coverage + verifies the package builds

### Test Files

| File | # Tests | Covers |
|------|---------|--------|
| `test_auth.py` | 13 | Auth detection priority, PAT header encoding, dispatcher |
| `test_server.py` | 8 | Project resolution, all 41 tools registered |
| `test_clients.py` | 21 | Response shaping, URL construction, identity formatting |

---

## Tool Categories & Client Mapping

| Category (# tools) | Client Module | Base URL |
|---------------------|---------------|----------|
| Pipelines & Builds (6) | `clients/pipelines.py` | `dev.azure.com/{org}` |
| Releases & Approvals (6) | `clients/releases.py` | `vsrm.dev.azure.com/{org}` |
| Git Repos + PRs (12) | `clients/git.py` | `dev.azure.com/{org}` |
| Boards & Work Items (11) | `clients/boards.py` | `dev.azure.com/{org}` |
| Test Management (3) | `clients/tests.py` | `dev.azure.com/{org}` |
| Wikis (3) | `clients/wiki.py` | `dev.azure.com/{org}` |

> **Note**: `releases.py` uses `vsrm.dev.azure.com` — a different base URL extracted via regex from `AZURE_DEVOPS_ORG_URL`.

---

## Conventions for Adding New Tools

1. **Create or update a client module** in `src/azure_devops_mcp/clients/` with the business logic function.
2. **Register a thin wrapper** in `server.py` using `@mcp.tool()` with a comprehensive docstring (the docstring becomes the tool description for AI clients).
3. **Lazy-import** the client function inside the tool function body using absolute imports (`from azure_devops_mcp.clients.X import ...`).
4. **Use `_resolve_project(project)`** to handle the optional project param.
5. **Return clean dicts** — shape the response, don't pass through raw API payloads.
6. **Include retry logic** in the client's `_api()` function for 429/5xx.
7. **Add tests** in `tests/test_clients.py` for response shaping.
8. **Add the tool name** to the `EXPECTED_TOOLS` list in `tests/test_server.py`.
9. **Add the tool to the README** tool table.

### Tool Function Signature Conventions

- All params have defaults (`str = ""`, `int = 0`, `bool = False`, `dict | None = None`).
- `project: str = ""` is always the first param.
- Docstrings use Google-style `Args:` sections.
- **Imports use absolute package paths**: `from azure_devops_mcp.clients.X import ...` (never bare `from clients.X`).

---

## Known Code Patterns / Quirks

- **`_api()` is duplicated** across all 6 client modules (not shared via a base class or util). If modifying retry logic, update all modules.
- **`_format_identity()` is duplicated** in `git.py`, `boards.py`, `releases.py` (not shared).
- `releases.py` does a **regex parse** of `AZURE_DEVOPS_ORG_URL` to construct the `vsrm.dev.azure.com` URL.
- `boards.py` work-item creation uses content-type `application/json-patch+json` (JSON Patch format required by Azure DevOps WIT APIs).
- `wiki.py` `create_or_update_wiki_page` uses `PUT` with optional `If-Match` header for optimistic concurrency.
- `git.py` `get_file_content` returns plain text (not JSON) — it sets `accept: text/plain`.
- Branch comparisons in `git.py` cap changed files at **100** to avoid huge payloads.
- Work item queries in `boards.py` cap results at **200** items.

---

## Publishing to PyPI

```bash
# Build
python -m build

# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

The `[project.scripts]` entry in `pyproject.toml` creates the `azure-devops-mcp` CLI command on install.
