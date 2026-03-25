"""Git repository and pull request operations for Azure DevOps."""

import os

import httpx

from azure_devops_mcp.auth import get_auth_header


def _get_org_url() -> str:
    url = os.getenv("AZURE_DEVOPS_ORG_URL")
    if not url:
        raise ValueError("AZURE_DEVOPS_ORG_URL is not set.")
    return url.rstrip("/")


def _api(
    method: str,
    url: str,
    params: dict | None = None,
    json_body: dict | None = None,
    content_type: str = "application/json",
    accept: str | None = None,
) -> dict | list | str:
    """Make an authenticated Azure DevOps REST API call with retry for 429/5xx."""
    headers = get_auth_header()
    headers["Content-Type"] = content_type
    if accept:
        headers["Accept"] = accept
    base_params = {"api-version": "7.1"}
    if params:
        base_params.update(params)

    import time

    max_retries = 3
    with httpx.Client(timeout=30) as client:
        for attempt in range(max_retries):
            resp = client.request(method, url, headers=headers, params=base_params, json=json_body)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries - 1:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(retry_after)
                    continue
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if ct.startswith("application/json"):
                return resp.json()
            return resp.text
    raise RuntimeError(f"Azure DevOps API request failed after {max_retries} retries")


def list_repositories(project: str) -> list[dict]:
    """List all Git repositories in a project."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories"
    data = _api("GET", url)
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "default_branch": r.get("defaultBranch"),
            "size": r.get("size"),
            "url": r.get("webUrl"),
            "is_disabled": r.get("isDisabled"),
        }
        for r in data.get("value", [])
    ]


def get_repository(project: str, repository_id: str) -> dict:
    """Get detailed information about a specific repository."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}"
    r = _api("GET", url)
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "default_branch": r.get("defaultBranch"),
        "size": r.get("size"),
        "url": r.get("webUrl"),
        "remote_url": r.get("remoteUrl"),
        "ssh_url": r.get("sshUrl"),
        "is_disabled": r.get("isDisabled"),
        "project": {
            "id": r.get("project", {}).get("id"),
            "name": r.get("project", {}).get("name"),
        },
    }


def list_branches(project: str, repository_id: str, filter_prefix: str = "") -> list[dict]:
    """List branches in a repository."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/refs"
    params = {"filter": f"heads/{filter_prefix}"}
    data = _api("GET", url, params=params)
    return [
        {
            "name": ref.get("name", "").replace("refs/heads/", ""),
            "object_id": ref.get("objectId"),
            "creator": _format_identity(ref.get("creator")),
        }
        for ref in data.get("value", [])
    ]


def get_commits(
    project: str,
    repository_id: str,
    branch: str = "",
    top: int = 20,
    author: str = "",
) -> list[dict]:
    """Get recent commits for a repository."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/commits"
    params: dict = {"$top": top}
    if branch:
        params["searchCriteria.itemVersion.version"] = branch
    if author:
        params["searchCriteria.author"] = author
    data = _api("GET", url, params=params)
    return [
        {
            "commit_id": c.get("commitId"),
            "comment": c.get("comment"),
            "author": c.get("author", {}).get("name"),
            "author_email": c.get("author", {}).get("email"),
            "author_date": c.get("author", {}).get("date"),
            "committer": c.get("committer", {}).get("name"),
            "committer_date": c.get("committer", {}).get("date"),
            "url": c.get("remoteUrl"),
        }
        for c in data.get("value", [])
    ]


def get_file_content(
    project: str,
    repository_id: str,
    path: str,
    branch: str = "",
) -> str:
    """Get the content of a file from a repository."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/items"
    params: dict = {"path": path, "includeContent": "true"}
    if branch:
        params["versionDescriptor.version"] = branch
        params["versionDescriptor.versionType"] = "branch"
    result = _api("GET", url, params=params, accept="text/plain")
    if isinstance(result, str):
        return result
    return str(result)


def list_pull_requests(
    project: str,
    repository_id: str,
    status: str = "active",
    top: int = 25,
    creator: str = "",
    reviewer: str = "",
) -> list[dict]:
    """List pull requests in a repository."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/pullrequests"
    params: dict = {"searchCriteria.status": status, "$top": top}
    if creator:
        params["searchCriteria.creatorId"] = creator
    if reviewer:
        params["searchCriteria.reviewerId"] = reviewer
    data = _api("GET", url, params=params)
    return [
        _format_pull_request(pr)
        for pr in data.get("value", [])
    ]


def get_pull_request(project: str, repository_id: str, pull_request_id: int) -> dict:
    """Get detailed information about a specific pull request."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/pullrequests/{pull_request_id}"
    pr = _api("GET", url)
    return _format_pull_request(pr)


def create_pull_request(
    project: str,
    repository_id: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str = "",
    reviewers: list[str] | None = None,
    is_draft: bool = False,
) -> dict:
    """Create a new pull request."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/pullrequests"

    # Ensure refs/heads/ prefix
    if not source_branch.startswith("refs/"):
        source_branch = f"refs/heads/{source_branch}"
    if not target_branch.startswith("refs/"):
        target_branch = f"refs/heads/{target_branch}"

    body: dict = {
        "sourceRefName": source_branch,
        "targetRefName": target_branch,
        "title": title,
        "description": description or "",
        "isDraft": is_draft,
    }
    if reviewers:
        body["reviewers"] = [{"id": r} for r in reviewers]

    pr = _api("POST", url, json_body=body)
    return _format_pull_request(pr)


def update_pull_request(
    project: str,
    repository_id: str,
    pull_request_id: int,
    status: str | None = None,
    title: str | None = None,
    description: str | None = None,
    auto_complete_set_by: str | None = None,
    merge_strategy: str | None = None,
) -> dict:
    """Update a pull request (change status, title, description, set auto-complete, etc.).

    Args:
        status: "active", "abandoned", or "completed" (to merge).
        merge_strategy: "noFastForward", "squash", "rebase", "rebaseMerge".
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/pullrequests/{pull_request_id}"

    body: dict = {}
    if status is not None:
        body["status"] = status
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if auto_complete_set_by is not None:
        body["autoCompleteSetBy"] = {"id": auto_complete_set_by}
    if merge_strategy is not None:
        body["completionOptions"] = {"mergeStrategy": merge_strategy}

    pr = _api("PATCH", url, json_body=body)
    return _format_pull_request(pr)


def get_pull_request_threads(project: str, repository_id: str, pull_request_id: int) -> list[dict]:
    """Get comment threads on a pull request."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/pullrequests/{pull_request_id}/threads"
    data = _api("GET", url)
    return [
        {
            "id": t.get("id"),
            "status": t.get("status"),
            "is_deleted": t.get("isDeleted"),
            "published_date": t.get("publishedDate"),
            "last_updated_date": t.get("lastUpdatedDate"),
            "thread_context": {
                "file_path": (t.get("threadContext") or {}).get("filePath"),
            } if t.get("threadContext") else None,
            "comments": [
                {
                    "id": c.get("id"),
                    "content": c.get("content"),
                    "author": _format_identity(c.get("author")),
                    "published_date": c.get("publishedDate"),
                    "comment_type": c.get("commentType"),
                }
                for c in t.get("comments", [])
            ],
        }
        for t in data.get("value", [])
    ]


def create_pull_request_comment(
    project: str,
    repository_id: str,
    pull_request_id: int,
    content: str,
    file_path: str | None = None,
    line_number: int | None = None,
    status: str = "active",
) -> dict:
    """Add a comment thread to a pull request.

    Args:
        content: The comment text (supports markdown).
        file_path: Optional file path for inline comments.
        line_number: Optional line number for inline comments (requires file_path).
        status: Thread status: "active", "fixed", "wontFix", "closed", "byDesign", "pending".
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/pullrequests/{pull_request_id}/threads"

    body: dict = {
        "comments": [{"parentCommentId": 0, "content": content, "commentType": 1}],
        "status": status,
    }
    if file_path:
        thread_context: dict = {"filePath": file_path}
        if line_number is not None:
            thread_context["rightFileStart"] = {"line": line_number, "offset": 1}
            thread_context["rightFileEnd"] = {"line": line_number, "offset": 1}
        body["threadContext"] = thread_context

    t = _api("POST", url, json_body=body)
    return {
        "id": t.get("id"),
        "status": t.get("status"),
        "comments": [
            {
                "id": c.get("id"),
                "content": c.get("content"),
                "author": _format_identity(c.get("author")),
            }
            for c in t.get("comments", [])
        ],
    }


def compare_branches(
    project: str,
    repository_id: str,
    base_branch: str,
    target_branch: str,
) -> dict:
    """Compare two branches and show the diff summary."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/git/repositories/{repository_id}/diffs/commits"
    params = {
        "baseVersion": base_branch,
        "baseVersionType": "branch",
        "targetVersion": target_branch,
        "targetVersionType": "branch",
    }
    data = _api("GET", url, params=params)
    changes = data.get("changes", [])
    return {
        "ahead_count": data.get("aheadCount"),
        "behind_count": data.get("behindCount"),
        "common_commit": data.get("commonCommit"),
        "change_count": len(changes),
        "changes": [
            {
                "change_type": c.get("changeType"),
                "path": c.get("item", {}).get("path"),
                "is_folder": c.get("item", {}).get("isFolder"),
            }
            for c in changes[:100]  # cap at 100 to avoid huge payloads
        ],
    }


def _format_pull_request(pr: dict) -> dict:
    """Format a pull request response into a clean dict."""
    return {
        "id": pr.get("pullRequestId"),
        "title": pr.get("title"),
        "description": pr.get("description"),
        "status": pr.get("status"),
        "is_draft": pr.get("isDraft"),
        "source_branch": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
        "target_branch": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
        "created_by": _format_identity(pr.get("createdBy")),
        "creation_date": pr.get("creationDate"),
        "merge_status": pr.get("mergeStatus"),
        "merge_id": pr.get("mergeId"),
        "reviewers": [
            {
                "name": _format_identity(r),
                "vote": r.get("vote"),
                "is_required": r.get("isRequired"),
            }
            for r in pr.get("reviewers", [])
        ],
        "url": pr.get("url"),
        "repository": {
            "id": pr.get("repository", {}).get("id"),
            "name": pr.get("repository", {}).get("name"),
        },
    }


def _format_identity(identity) -> str | None:
    """Format an identity reference to a readable string."""
    if identity is None:
        return None
    if isinstance(identity, dict):
        return identity.get("displayName") or identity.get("uniqueName")
    return str(identity)
