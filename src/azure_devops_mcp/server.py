"""
Azure DevOps MCP Server

Exposes Azure DevOps pipelines and boards as MCP tools.
Supports PAT, Service Principal, Managed Identity, and Device Code auth.
"""

import os
import sys

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
load_dotenv()

mcp = FastMCP(
    "azure-devops",
    instructions=(
        "Azure DevOps MCP server. Provides tools to interact with Azure DevOps "
        "pipelines (list, runs, logs, trigger, build artifacts), classic releases "
        "(list definitions, list/get/create releases, approvals), "
        "Git repositories (list repos, branches, commits, file content, compare branches), "
        "pull requests (list, get, create, update, comment threads), "
        "boards/work items (list boards, get/create/update/delete work items, "
        "comments, relation links, WIQL queries, saved queries), "
        "test management (test runs, results, code coverage), "
        "and wikis (list, get/create pages). "
        "Most tools require a 'project' parameter — the Azure DevOps project name."
    ),
)

# Default project from environment
DEFAULT_PROJECT = os.getenv("AZURE_DEVOPS_PROJECT", "")


def _resolve_project(project: str | None) -> str:
    """Resolve project name, falling back to the default."""
    p = project or DEFAULT_PROJECT
    if not p:
        raise ValueError(
            "Project name is required. Pass it as a parameter or set AZURE_DEVOPS_PROJECT env var."
        )
    return p


# ──────────────────────────────────────────────
# Pipeline Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_pipelines(project: str = "") -> list[dict]:
    """
    List all pipelines in an Azure DevOps project.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
    """
    from azure_devops_mcp.clients.pipelines import list_pipelines as _list_pipelines
    return _list_pipelines(_resolve_project(project))


@mcp.tool()
def get_pipeline_runs(project: str = "", pipeline_id: int = 0, top: int = 10) -> list[dict]:
    """
    Get recent runs for a specific pipeline.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        pipeline_id: The ID of the pipeline.
        top: Maximum number of runs to return (default: 10).
    """
    from azure_devops_mcp.clients.pipelines import get_pipeline_runs as _get_pipeline_runs
    return _get_pipeline_runs(_resolve_project(project), pipeline_id, top)


@mcp.tool()
def get_pipeline_run_logs(project: str = "", pipeline_id: int = 0, run_id: int = 0) -> list[dict]:
    """
    Get logs for a specific pipeline run.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        pipeline_id: The ID of the pipeline.
        run_id: The ID of the pipeline run.
    """
    from azure_devops_mcp.clients.pipelines import get_pipeline_run_logs as _get_pipeline_run_logs
    return _get_pipeline_run_logs(_resolve_project(project), pipeline_id, run_id)


@mcp.tool()
def trigger_pipeline(project: str = "", pipeline_id: int = 0, parameters: dict | None = None) -> dict:
    """
    Trigger a new pipeline run.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        pipeline_id: The ID of the pipeline to trigger.
        parameters: Optional template parameters to pass to the pipeline as key-value pairs.
    """
    from azure_devops_mcp.clients.pipelines import trigger_pipeline as _trigger_pipeline
    return _trigger_pipeline(_resolve_project(project), pipeline_id, parameters)


# ──────────────────────────────────────────────
# Build Artifact Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_build_artifacts(project: str = "", build_id: int = 0) -> list[dict]:
    """
    List artifacts produced by a build.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        build_id: The build ID.
    """
    from azure_devops_mcp.clients.pipelines import list_build_artifacts as _list_build_artifacts
    return _list_build_artifacts(_resolve_project(project), build_id)


@mcp.tool()
def get_artifact_download_url(project: str = "", build_id: int = 0, artifact_name: str = "") -> dict:
    """
    Get the download URL for a specific build artifact.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        build_id: The build ID.
        artifact_name: The name of the artifact.
    """
    from azure_devops_mcp.clients.pipelines import get_artifact_download_url as _get_artifact_download_url
    return _get_artifact_download_url(_resolve_project(project), build_id, artifact_name)


# ──────────────────────────────────────────────
# Release Tools (classic releases via vsrm.dev.azure.com)
# ──────────────────────────────────────────────


@mcp.tool()
def list_release_definitions(project: str = "", top: int = 50) -> list[dict]:
    """
    List all classic release definitions (release pipelines) in a project.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        top: Maximum number of definitions to return (default: 50).
    """
    from azure_devops_mcp.clients.releases import list_release_definitions as _list_release_definitions
    return _list_release_definitions(_resolve_project(project), top)


@mcp.tool()
def list_releases(project: str = "", definition_id: int = 0, top: int = 25) -> list[dict]:
    """
    List releases, optionally filtered by a release definition.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        definition_id: Optional release definition ID to filter by. 0 means all.
        top: Maximum number of releases to return (default: 25).
    """
    from azure_devops_mcp.clients.releases import list_releases as _list_releases
    return _list_releases(_resolve_project(project), definition_id or None, top)


@mcp.tool()
def get_release(project: str = "", release_id: int = 0) -> dict:
    """
    Get detailed information about a specific release, including environment/stage status.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        release_id: The ID of the release.
    """
    from azure_devops_mcp.clients.releases import get_release as _get_release
    return _get_release(_resolve_project(project), release_id)


@mcp.tool()
def create_release(
    project: str = "",
    definition_id: int = 0,
    description: str = "",
    artifacts: list[dict] | None = None,
) -> dict:
    """
    Create (trigger) a new release from a classic release definition.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        definition_id: The release definition ID to create a release from.
        description: Optional description for the release.
        artifacts: Optional list of artifact version overrides. Each dict should have:
                   - alias (str): artifact source alias
                   - version_id (str): specific version/build ID
                   - version_name (str): display name for the version
    """
    from azure_devops_mcp.clients.releases import create_release as _create_release
    return _create_release(_resolve_project(project), definition_id, description, artifacts)


# ──────────────────────────────────────────────
# Release Approval Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_release_approvals(
    project: str = "",
    status: str = "pending",
    top: int = 25,
    assigned_to: str = "",
) -> list[dict]:
    """
    List release approvals, optionally filtered by status.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        status: Filter by status: "pending", "approved", "rejected", "reassigned",
                "canceled", "skipped", "undefined". Default is "pending".
        top: Maximum number of approvals to return (default: 25).
        assigned_to: Optional filter by approver display name or unique name.
    """
    from azure_devops_mcp.clients.releases import list_release_approvals as _list_release_approvals
    return _list_release_approvals(_resolve_project(project), status, top, assigned_to)


@mcp.tool()
def update_release_approval(
    project: str = "",
    approval_id: int = 0,
    status: str = "",
    comments: str = "",
) -> dict:
    """
    Approve or reject a release approval.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        approval_id: The approval ID.
        status: "approved" or "rejected".
        comments: Optional comments for the approval decision.
    """
    from azure_devops_mcp.clients.releases import update_release_approval as _update_release_approval
    if not status:
        raise ValueError("status is required. Use 'approved' or 'rejected'.")
    return _update_release_approval(_resolve_project(project), approval_id, status, comments)


# ──────────────────────────────────────────────
# Board Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_boards(project: str = "", team: str = "") -> list[dict]:
    """
    List all boards for a project/team.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        team: Team name. If not specified, uses the project's default team.
    """
    from azure_devops_mcp.clients.boards import list_boards as _list_boards
    return _list_boards(_resolve_project(project), team or None)


@mcp.tool()
def get_board_work_items(project: str = "", board: str = "", team: str = "") -> dict:
    """
    Get work items on a specific board along with board columns.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        board: Name of the board (e.g., "Stories", "Bugs").
        team: Team name. If not specified, uses the project's default team.
    """
    from azure_devops_mcp.clients.boards import get_board_work_items as _get_board_work_items
    return _get_board_work_items(_resolve_project(project), board, team or None)


# ──────────────────────────────────────────────
# Work Item Tools
# ──────────────────────────────────────────────


@mcp.tool()
def get_work_item(project: str = "", work_item_id: int = 0) -> dict:
    """
    Get detailed information about a specific work item.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        work_item_id: The ID of the work item.
    """
    from azure_devops_mcp.clients.boards import get_work_item as _get_work_item
    return _get_work_item(_resolve_project(project), work_item_id)


@mcp.tool()
def create_work_item(
    project: str = "",
    work_item_type: str = "",
    title: str = "",
    description: str = "",
    assigned_to: str = "",
    area_path: str = "",
    iteration_path: str = "",
    priority: int | None = None,
    tags: str = "",
    additional_fields: dict | None = None,
    parent_id: int | None = None,
) -> dict:
    """
    Create a new work item.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        work_item_type: Type of work item (e.g., "Bug", "User Story", "Task", "Epic", "Feature").
        title: Title of the work item.
        description: HTML description of the work item.
        assigned_to: Display name or email of the person to assign to.
        area_path: Area path (e.g., "MyProject\\Team A").
        iteration_path: Iteration path (e.g., "MyProject\\Sprint 1").
        priority: Priority (1=Critical, 2=High, 3=Medium, 4=Low).
        tags: Semicolon-separated tags (e.g., "frontend; urgent").
        additional_fields: Dict of additional field paths and values.
        parent_id: Optional ID of a parent work item to link to.
    """
    from azure_devops_mcp.clients.boards import create_work_item as _create_work_item
    return _create_work_item(
        _resolve_project(project),
        work_item_type, title, description,
        assigned_to, area_path, iteration_path,
        priority, tags, additional_fields, parent_id,
    )


@mcp.tool()
def update_work_item(
    project: str = "",
    work_item_id: int = 0,
    fields: dict | None = None,
    add_links: list[dict] | None = None,
) -> dict:
    """
    Update an existing work item's fields and/or add relation links.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        work_item_id: The ID of the work item to update.
        fields: Dict mapping field names to new values. Example:
                {"System.Title": "New Title", "System.State": "Active",
                 "System.AssignedTo": "user@example.com"}
        add_links: List of relation links to add. Each dict must have:
                   - target_id (int): ID of the work item to link to.
                   - link_type (str): "parent", "child", "related", "predecessor",
                     "successor", or a fully-qualified relation type.
                   - comment (str, optional): Comment for the link.
                   Example: [{"target_id": 100, "link_type": "parent"}]
    """
    from azure_devops_mcp.clients.boards import update_work_item as _update_work_item
    if not fields and not add_links:
        raise ValueError("At least one of 'fields' or 'add_links' must be provided.")
    return _update_work_item(_resolve_project(project), work_item_id, fields, add_links)


@mcp.tool()
def query_work_items(project: str = "", query: str = "") -> list[dict]:
    """
    Execute a WIQL (Work Item Query Language) query.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        query: WIQL query string. Example:
               "SELECT [System.Id], [System.Title], [System.State]
                FROM workitems
                WHERE [System.WorkItemType] = 'Bug'
                AND [System.State] = 'Active'
                ORDER BY [System.CreatedDate] DESC"
    """
    from azure_devops_mcp.clients.boards import query_work_items as _query_work_items
    if not query:
        raise ValueError("query parameter is required. Provide a valid WIQL query string.")
    return _query_work_items(_resolve_project(project), query)


# ──────────────────────────────────────────────
# Work Item Comment Tools
# ──────────────────────────────────────────────


@mcp.tool()
def get_work_item_comments(project: str = "", work_item_id: int = 0, top: int = 50) -> list[dict]:
    """
    Get comments on a work item.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        work_item_id: The ID of the work item.
        top: Maximum number of comments to return (default: 50).
    """
    from azure_devops_mcp.clients.boards import get_work_item_comments as _get_work_item_comments
    return _get_work_item_comments(_resolve_project(project), work_item_id, top)


@mcp.tool()
def add_work_item_comment(project: str = "", work_item_id: int = 0, text: str = "") -> dict:
    """
    Add a comment to a work item.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        work_item_id: The ID of the work item.
        text: The comment text (supports HTML).
    """
    from azure_devops_mcp.clients.boards import add_work_item_comment as _add_work_item_comment
    if not text:
        raise ValueError("text parameter is required.")
    return _add_work_item_comment(_resolve_project(project), work_item_id, text)


@mcp.tool()
def delete_work_item(project: str = "", work_item_id: int = 0, destroy: bool = False) -> dict:
    """
    Delete a work item (move to recycle bin, or permanently destroy).

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        work_item_id: The ID of the work item to delete.
        destroy: If True, permanently delete. If False (default), move to recycle bin.
    """
    from azure_devops_mcp.clients.boards import delete_work_item as _delete_work_item
    return _delete_work_item(_resolve_project(project), work_item_id, destroy)


# ──────────────────────────────────────────────
# Saved Query Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_saved_queries(project: str = "", depth: int = 2) -> list[dict]:
    """
    List saved work item queries (folders and queries).

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        depth: How deep to recurse into query folders (default: 2).
    """
    from azure_devops_mcp.clients.boards import list_saved_queries as _list_saved_queries
    return _list_saved_queries(_resolve_project(project), depth)


@mcp.tool()
def run_saved_query(project: str = "", query_id: str = "") -> list[dict]:
    """
    Execute a saved query by its ID and return work item details.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        query_id: The saved query GUID.
    """
    from azure_devops_mcp.clients.boards import run_saved_query as _run_saved_query
    if not query_id:
        raise ValueError("query_id parameter is required.")
    return _run_saved_query(_resolve_project(project), query_id)


# ──────────────────────────────────────────────
# Git Repository Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_repositories(project: str = "") -> list[dict]:
    """
    List all Git repositories in a project.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
    """
    from azure_devops_mcp.clients.git import list_repositories as _list_repositories
    return _list_repositories(_resolve_project(project))


@mcp.tool()
def get_repository(project: str = "", repository_id: str = "") -> dict:
    """
    Get detailed information about a specific Git repository.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
    """
    from azure_devops_mcp.clients.git import get_repository as _get_repository
    return _get_repository(_resolve_project(project), repository_id)


@mcp.tool()
def list_branches(project: str = "", repository_id: str = "", filter_prefix: str = "") -> list[dict]:
    """
    List branches in a Git repository.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        filter_prefix: Optional prefix to filter branch names (e.g., "feature/").
    """
    from azure_devops_mcp.clients.git import list_branches as _list_branches
    return _list_branches(_resolve_project(project), repository_id, filter_prefix)


@mcp.tool()
def get_commits(
    project: str = "",
    repository_id: str = "",
    branch: str = "",
    top: int = 20,
    author: str = "",
) -> list[dict]:
    """
    Get recent commits for a Git repository.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        branch: Optional branch name to filter commits.
        top: Maximum number of commits to return (default: 20).
        author: Optional author name to filter commits.
    """
    from azure_devops_mcp.clients.git import get_commits as _get_commits
    return _get_commits(_resolve_project(project), repository_id, branch, top, author)


@mcp.tool()
def get_file_content(
    project: str = "",
    repository_id: str = "",
    path: str = "",
    branch: str = "",
) -> str:
    """
    Get the content of a file from a Git repository.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        path: File path in the repository (e.g., "/src/main.py").
        branch: Optional branch name (defaults to the repository's default branch).
    """
    from azure_devops_mcp.clients.git import get_file_content as _get_file_content
    return _get_file_content(_resolve_project(project), repository_id, path, branch)


@mcp.tool()
def compare_branches(
    project: str = "",
    repository_id: str = "",
    base_branch: str = "",
    target_branch: str = "",
) -> dict:
    """
    Compare two branches and show the diff summary.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        base_branch: The base branch name.
        target_branch: The target branch name.
    """
    from azure_devops_mcp.clients.git import compare_branches as _compare_branches
    return _compare_branches(_resolve_project(project), repository_id, base_branch, target_branch)


# ──────────────────────────────────────────────
# Pull Request Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_pull_requests(
    project: str = "",
    repository_id: str = "",
    status: str = "active",
    top: int = 25,
    creator: str = "",
    reviewer: str = "",
) -> list[dict]:
    """
    List pull requests in a Git repository.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        status: Filter by status: "active", "completed", "abandoned", "all" (default: "active").
        top: Maximum number of pull requests to return (default: 25).
        creator: Optional filter by creator ID.
        reviewer: Optional filter by reviewer ID.
    """
    from azure_devops_mcp.clients.git import list_pull_requests as _list_pull_requests
    return _list_pull_requests(_resolve_project(project), repository_id, status, top, creator, reviewer)


@mcp.tool()
def get_pull_request(project: str = "", repository_id: str = "", pull_request_id: int = 0) -> dict:
    """
    Get detailed information about a specific pull request.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        pull_request_id: The pull request ID.
    """
    from azure_devops_mcp.clients.git import get_pull_request as _get_pull_request
    return _get_pull_request(_resolve_project(project), repository_id, pull_request_id)


@mcp.tool()
def create_pull_request(
    project: str = "",
    repository_id: str = "",
    source_branch: str = "",
    target_branch: str = "",
    title: str = "",
    description: str = "",
    reviewers: list[str] | None = None,
    is_draft: bool = False,
) -> dict:
    """
    Create a new pull request.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        source_branch: Source branch name (e.g., "feature/my-feature").
        target_branch: Target branch name (e.g., "main").
        title: Title of the pull request.
        description: Optional description/body of the pull request.
        reviewers: Optional list of reviewer IDs.
        is_draft: Whether to create as a draft PR (default: False).
    """
    from azure_devops_mcp.clients.git import create_pull_request as _create_pull_request
    return _create_pull_request(
        _resolve_project(project), repository_id,
        source_branch, target_branch, title, description,
        reviewers, is_draft,
    )


@mcp.tool()
def update_pull_request(
    project: str = "",
    repository_id: str = "",
    pull_request_id: int = 0,
    status: str | None = None,
    title: str | None = None,
    description: str | None = None,
    auto_complete_set_by: str | None = None,
    merge_strategy: str | None = None,
) -> dict:
    """
    Update a pull request (change status, title, description, set auto-complete).

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        pull_request_id: The pull request ID.
        status: "active", "abandoned", or "completed" (to merge).
        title: New title for the pull request.
        description: New description for the pull request.
        auto_complete_set_by: User ID to set auto-complete by.
        merge_strategy: "noFastForward", "squash", "rebase", "rebaseMerge".
    """
    from azure_devops_mcp.clients.git import update_pull_request as _update_pull_request
    return _update_pull_request(
        _resolve_project(project), repository_id, pull_request_id,
        status, title, description, auto_complete_set_by, merge_strategy,
    )


@mcp.tool()
def get_pull_request_threads(
    project: str = "",
    repository_id: str = "",
    pull_request_id: int = 0,
) -> list[dict]:
    """
    Get comment threads on a pull request.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        pull_request_id: The pull request ID.
    """
    from azure_devops_mcp.clients.git import get_pull_request_threads as _get_pull_request_threads
    return _get_pull_request_threads(_resolve_project(project), repository_id, pull_request_id)


@mcp.tool()
def create_pull_request_comment(
    project: str = "",
    repository_id: str = "",
    pull_request_id: int = 0,
    content: str = "",
    file_path: str | None = None,
    line_number: int | None = None,
    status: str = "active",
) -> dict:
    """
    Add a comment thread to a pull request.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        repository_id: The repository ID or name.
        pull_request_id: The pull request ID.
        content: The comment text (supports markdown).
        file_path: Optional file path for inline comments.
        line_number: Optional line number for inline comments (requires file_path).
        status: Thread status: "active", "fixed", "wontFix", "closed", "byDesign", "pending".
    """
    from azure_devops_mcp.clients.git import create_pull_request_comment as _create_pull_request_comment
    if not content:
        raise ValueError("content parameter is required.")
    return _create_pull_request_comment(
        _resolve_project(project), repository_id, pull_request_id,
        content, file_path, line_number, status,
    )


# ──────────────────────────────────────────────
# Test Management Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_test_runs(project: str = "", top: int = 25, state: str = "") -> list[dict]:
    """
    List test runs in a project.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        top: Maximum number of runs to return (default: 25).
        state: Optional filter by state (e.g., "Completed", "InProgress", "Aborted").
    """
    from azure_devops_mcp.clients.tests import list_test_runs as _list_test_runs
    return _list_test_runs(_resolve_project(project), top, state)


@mcp.tool()
def get_test_run_results(
    project: str = "",
    run_id: int = 0,
    top: int = 200,
    outcome: str = "",
) -> list[dict]:
    """
    Get test results for a specific test run.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        run_id: The test run ID.
        top: Maximum number of results to return (default: 200).
        outcome: Optional filter by outcome (e.g., "Passed", "Failed", "NotExecuted").
    """
    from azure_devops_mcp.clients.tests import get_test_run_results as _get_test_run_results
    return _get_test_run_results(_resolve_project(project), run_id, top, outcome)


@mcp.tool()
def get_code_coverage(project: str = "", build_id: int = 0) -> dict:
    """
    Get code coverage summary for a build.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        build_id: The build ID to get coverage for.
    """
    from azure_devops_mcp.clients.tests import get_code_coverage as _get_code_coverage
    return _get_code_coverage(_resolve_project(project), build_id)


# ──────────────────────────────────────────────
# Wiki Tools
# ──────────────────────────────────────────────


@mcp.tool()
def list_wikis(project: str = "") -> list[dict]:
    """
    List all wikis in a project.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
    """
    from azure_devops_mcp.clients.wiki import list_wikis as _list_wikis
    return _list_wikis(_resolve_project(project))


@mcp.tool()
def get_wiki_page(
    project: str = "",
    wiki_id: str = "",
    path: str = "/",
    include_content: bool = True,
) -> dict:
    """
    Get a wiki page by path.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        wiki_id: The wiki identifier (name or ID).
        path: Page path (e.g., "/Home", "/Release Notes/v2"). Defaults to root.
        include_content: Whether to include the page markdown content (default: True).
    """
    from azure_devops_mcp.clients.wiki import get_wiki_page as _get_wiki_page
    return _get_wiki_page(_resolve_project(project), wiki_id, path, include_content)


@mcp.tool()
def create_or_update_wiki_page(
    project: str = "",
    wiki_id: str = "",
    path: str = "",
    content: str = "",
    comment: str = "",
    if_match: str = "",
) -> dict:
    """
    Create or update a wiki page.

    Args:
        project: Azure DevOps project name. Uses default if not specified.
        wiki_id: The wiki identifier (name or ID).
        path: Page path (e.g., "/Release Notes/v3").
        content: Markdown content for the page.
        comment: Optional commit comment.
        if_match: ETag for optimistic concurrency (required for updates, empty for creates).
    """
    from azure_devops_mcp.clients.wiki import create_or_update_wiki_page as _create_or_update_wiki_page
    return _create_or_update_wiki_page(
        _resolve_project(project), wiki_id, path, content, comment, if_match,
    )


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
