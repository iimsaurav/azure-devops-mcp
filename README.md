# Azure DevOps MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes **41 Azure DevOps tools** to AI assistants — covering pipelines, Git repositories, pull requests, releases, boards, work items, test management, and wikis.

**Authentication**: Azure Entra device code flow — no app registration required.

## What It Can Do

| Category | Tools | Highlights |
|----------|-------|------------|
| **Pipelines & Builds** | 6 | List pipelines, view runs/logs, trigger builds, browse build artifacts |
| **Releases & Approvals** | 6 | List/create releases, view release details, list/approve/reject approvals |
| **Git Repositories** | 6 | List repos, browse branches, view commits, read file content, compare branches |
| **Pull Requests** | 6 | List/create/update PRs, read comment threads, add comments (inline or general) |
| **Boards & Work Items** | 10 | List boards, get/create/update/delete work items, comments, WIQL queries, saved queries |
| **Test Management** | 3 | List test runs, view test results, get code coverage |
| **Wikis** | 3 | List wikis, read pages, create/update pages |
| | **41 total** | |

## Prerequisites

- Python 3.10+
- Access to an Azure DevOps organization (dev.azure.com)

## Installation

### From PyPI (recommended)

```bash
pip install azure-devops-mcp
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install azure-devops-mcp
```

### From source

```bash
git clone <your-repo-url>
cd azure-devops-mcp
pip install -e .
```

## Quick Start

After installing, follow these 3 steps:

### Step 1: Install

```bash
pip install azure-devops-mcp
```

### Step 2: Add to your AI editor

Open your editor's MCP config file and add the server. Here's VS Code as an example (`.vscode/mcp.json`):

**Option A — With a PAT (simplest, no browser prompt):**

```json
{
  "servers": {
    "azure-devops": {
      "command": "azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/YOUR-ORG",
        "AZURE_DEVOPS_PAT": "YOUR-PERSONAL-ACCESS-TOKEN"
      }
    }
  }
}
```

> To create a PAT: [Azure DevOps → User Settings → Personal Access Tokens → New Token](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate).

**Option B — With Device Code Flow (no PAT needed):**

First, log in once from your terminal:

```bash
export AZURE_DEVOPS_ORG_URL=https://dev.azure.com/YOUR-ORG
azure-devops-mcp auth login
```

This opens your browser, you sign in, and the token is cached locally. Then add to your editor — no PAT required:

```json
{
  "servers": {
    "azure-devops": {
      "command": "azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/YOUR-ORG"
      }
    }
  }
}
```

> Token is cached at `~/.azure-devops-mcp/token_cache.json` and auto-refreshes (~90 days).
> Run `azure-devops-mcp auth status` to check your login state.

### Step 3: Use it

Open your AI assistant (Copilot Chat, Claude, etc.) and ask:

```
List all pipelines in my project
```

The server handles authentication and API calls — the AI tool sees 41 Azure DevOps commands automatically.

---

## Configuration

Set these environment variables (via your shell, `.env` file, or MCP client config):

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_DEVOPS_ORG_URL` | **Yes** | Your Azure DevOps org URL (e.g., `https://dev.azure.com/your-organization`) |
| `AZURE_DEVOPS_PROJECT` | No | Default project (can be overridden per tool call) |

## Authentication

The server supports **4 authentication methods**, auto-detected from environment variables:

### Method 1: Personal Access Token (PAT) — simplest

Best for: scripts, personal use, CI/CD pipelines.

| Variable | Description |
|----------|-------------|
| `AZURE_DEVOPS_PAT` | Your [Personal Access Token](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate) |

```json
"env": {
  "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/my-org",
  "AZURE_DEVOPS_PAT": "your-pat-here"
}
```

### Method 2: Service Principal (Client Credentials) — for apps

Best for: registered Azure AD applications, service-to-service, automated workflows.

| Variable | Description |
|----------|-------------|
| `AZURE_CLIENT_ID` | Application (client) ID from your Azure AD app registration |
| `AZURE_CLIENT_SECRET` | Client secret for the app |
| `AZURE_TENANT_ID` | Azure AD tenant ID |

```json
"env": {
  "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/my-org",
  "AZURE_CLIENT_ID": "your-app-id",
  "AZURE_CLIENT_SECRET": "your-secret",
  "AZURE_TENANT_ID": "your-tenant-id"
}
```

### Method 3: Managed Identity — for Azure-hosted environments

Best for: running on Azure VMs, App Service, Azure Functions, AKS. No credentials to manage.

```bash
pip install azure-devops-mcp[managed-identity]
```

| Variable | Description |
|----------|-------------|
| `AZURE_USE_MANAGED_IDENTITY` | Set to `true` to enable |
| `AZURE_CLIENT_ID` | *(optional)* Client ID for user-assigned managed identity |

```json
"env": {
  "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/my-org",
  "AZURE_USE_MANAGED_IDENTITY": "true"
}
```

### Method 4: Device Code Flow — interactive (default)

Best for: developers running locally. No PAT or app registration needed.

**Recommended:** Pre-authenticate from your terminal before configuring your AI editor:

```bash
export AZURE_DEVOPS_ORG_URL=https://dev.azure.com/my-org
azure-devops-mcp auth login    # Opens browser, caches token
azure-devops-mcp auth status   # Verify login state
```

The browser opens automatically. After you sign in, the token is cached at `~/.azure-devops-mcp/token_cache.json` and auto-refreshes (~90 days).

If you skip `auth login`, the server will prompt via stderr on the first API call — but most AI editors don't display stderr, so pre-authenticating is strongly recommended.

**Priority**: PAT → Client Credentials → Managed Identity → Device Code. The first method detected wins.

### Setting Environment Variables

There are 3 ways to pass your configuration:

**Option A — In your AI editor's MCP config** *(recommended)*

Every MCP-compatible editor has an `"env"` block in its config. This is the easiest approach — just add your variables there. See the [Integration](#integration) section below for editor-specific examples.

**Option B — Via a `.env` file**

Create a `.env` file in your working directory (use `.env.example` as a template):

```env
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/my-org
AZURE_DEVOPS_PAT=my-pat-token
```

The server loads it automatically on startup via `python-dotenv`.

**Option C — Via shell environment** *(CI/CD, Docker, manual runs)*

```bash
export AZURE_DEVOPS_ORG_URL=https://dev.azure.com/my-org
export AZURE_DEVOPS_PAT=my-pat-token
azure-devops-mcp
```

## Integration

After installing via pip, the `azure-devops-mcp` command is available on your PATH. Configure your AI tool:

### VS Code (GitHub Copilot / Copilot Chat)

Add to `.vscode/mcp.json` in your workspace (or User Settings JSON under `mcp.servers`):

```json
{
  "servers": {
    "azure-devops": {
      "command": "azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/your-organization",
        "AZURE_DEVOPS_PROJECT": "your-default-project"
      }
    }
  }
}
```

### Claude Desktop

Add to your Claude Desktop config file:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/your-organization",
        "AZURE_DEVOPS_PROJECT": "your-default-project"
      }
    }
  }
}
```

### Claude Code (Cortex Code)

```bash
claude mcp add azure-devops -- azure-devops-mcp
```

Then set environment variables in your shell or Claude config.

### Cursor

Add to `.cursor/mcp.json` in your workspace:

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/your-organization",
        "AZURE_DEVOPS_PROJECT": "your-default-project",
        "AZURE_TENANT_ID": "your-tenant-id-or-organizations"
      }
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/your-organization",
        "AZURE_DEVOPS_PROJECT": "your-default-project"
      }
    }
  }
}
```

### Any MCP-compatible client

The server communicates over **stdio**. Point any MCP client at:

```
azure-devops-mcp
```

### Running from source (alternative)

If you cloned the repo instead of installing via pip:

```json
{
  "servers": {
    "azure-devops": {
      "command": "uv",
      "args": ["run", "python", "-m", "azure_devops_mcp"],
      "cwd": "/path/to/azure-devops-mcp",
      "env": {
        "AZURE_DEVOPS_ORG_URL": "https://dev.azure.com/your-organization",
        "AZURE_DEVOPS_PROJECT": "your-default-project"
      }
    }
  }
}
```

## All 41 Tools

### Pipelines & Build Artifacts

| Tool | Description |
|------|-------------|
| `list_pipelines` | List all YAML pipelines in a project |
| `get_pipeline_runs` | Get recent runs for a pipeline |
| `get_pipeline_run_logs` | Fetch full logs for a pipeline run |
| `trigger_pipeline` | Trigger a new pipeline run with optional template parameters |
| `list_build_artifacts` | List artifacts produced by a build |
| `get_artifact_download_url` | Get the download URL for a specific build artifact |

### Releases & Approvals

| Tool | Description |
|------|-------------|
| `list_release_definitions` | List classic release definitions (release pipelines) |
| `list_releases` | List releases, optionally filtered by definition |
| `get_release` | Get release detail including environment/stage status |
| `create_release` | Create a release with optional artifact version overrides |
| `list_release_approvals` | List pending (or other status) release approvals |
| `update_release_approval` | Approve or reject a release approval |

### Git Repositories

| Tool | Description |
|------|-------------|
| `list_repositories` | List all Git repositories in a project |
| `get_repository` | Get detailed info about a repository (URLs, default branch, etc.) |
| `list_branches` | List branches, optionally filtered by prefix |
| `get_commits` | Get recent commits, optionally filtered by branch or author |
| `get_file_content` | Read a file's content from a repository |
| `compare_branches` | Compare two branches (ahead/behind count + changed files) |

### Pull Requests

| Tool | Description |
|------|-------------|
| `list_pull_requests` | List PRs by status (active/completed/abandoned) |
| `get_pull_request` | Get PR detail (reviewers, merge status, etc.) |
| `create_pull_request` | Create a new PR with optional reviewers and draft mode |
| `update_pull_request` | Update PR status, title, description, auto-complete, merge strategy |
| `get_pull_request_threads` | Get all comment threads on a PR |
| `create_pull_request_comment` | Add a comment (general or inline on a specific file/line) |

### Boards & Work Items

| Tool | Description |
|------|-------------|
| `list_boards` | List boards for a project/team |
| `get_board_work_items` | Get work items on a board with column info |
| `get_work_item` | Get full work item detail (fields, relations, estimates) |
| `create_work_item` | Create a Bug, User Story, Task, Epic, or Feature |
| `update_work_item` | Update fields and/or add relation links |
| `delete_work_item` | Delete a work item (recycle bin or permanent) |
| `query_work_items` | Execute an arbitrary WIQL query |
| `get_work_item_comments` | Get comments on a work item |
| `add_work_item_comment` | Add a comment to a work item |
| `list_saved_queries` | List saved query folders and queries |
| `run_saved_query` | Execute a saved query by its ID |

### Test Management

| Tool | Description |
|------|-------------|
| `list_test_runs` | List test runs, optionally filtered by state |
| `get_test_run_results` | Get test results for a run (pass/fail/error details) |
| `get_code_coverage` | Get code coverage summary for a build |

### Wikis

| Tool | Description |
|------|-------------|
| `list_wikis` | List all wikis in a project |
| `get_wiki_page` | Get a wiki page's content by path |
| `create_or_update_wiki_page` | Create or update a wiki page with markdown content |

## Example Prompts

```
List all pipelines in the "MyProject" project
```

```
Show me the last 5 runs for pipeline 42
```

```
List all active pull requests in the "backend-api" repository
```

```
Create a pull request from feature/login to main titled "Add login page"
```

```
Show me pending release approvals
```

```
Approve release approval 1234 with comment "Looks good, deploying to prod"
```

```
Query all active bugs assigned to me:
SELECT [System.Id], [System.Title] FROM workitems
WHERE [System.WorkItemType] = 'Bug' AND [System.State] = 'Active'
AND [System.AssignedTo] = @Me
```

```
Get the wiki page at /Runbooks/Deployment from the project wiki
```

```
Show test results for test run 567 — only failures
```

```
Compare the main and develop branches in the "frontend" repo
```

## Development

Run the MCP dev inspector to test tools interactively:

```bash
uv run mcp dev src/azure_devops_mcp/server.py
```

## Architecture

```
azure-devops-mcp/
├── src/azure_devops_mcp/
│   ├── __init__.py            # Package init + version
│   ├── __main__.py            # CLI entry point (azure-devops-mcp command)
│   ├── server.py              # MCP server — registers all 41 tools
│   ├── auth.py                # MSAL device-code auth (no app registration needed)
│   └── clients/
│       ├── pipelines.py       # Pipeline + build artifact API calls
│       ├── releases.py        # Classic release + approval API calls
│       ├── git.py             # Git repos, branches, commits, PRs
│       ├── boards.py          # Boards, work items, comments, saved queries
│       ├── tests.py           # Test runs, results, code coverage
│       └── wiki.py            # Wiki pages
├── .env.example               # Environment variable template
├── pyproject.toml             # Python project config (PyPI metadata + build)
└── README.md
```

All client modules include retry logic with exponential backoff for `429 Too Many Requests` and `5xx` server errors.

## License

[MIT](LICENSE)
