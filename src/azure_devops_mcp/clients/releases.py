"""Release operations for Azure DevOps (classic releases).

Classic releases use a different base URL: vsrm.dev.azure.com
"""

import os
import re

import httpx

from azure_devops_mcp.auth import get_auth_header


def _get_rm_url() -> str:
    """Get the Release Management base URL (vsrm.dev.azure.com)."""
    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    if not org_url:
        raise ValueError("AZURE_DEVOPS_ORG_URL is not set.")
    # Extract org name from https://dev.azure.com/{org} or https://{org}.visualstudio.com
    url = org_url.rstrip("/")
    match = re.search(r"dev\.azure\.com/([^/]+)", url)
    if not match:
        match = re.search(r"^https?://([^.]+)\.visualstudio\.com", url)
    if not match:
        raise ValueError(
            f"Cannot extract organization from AZURE_DEVOPS_ORG_URL: {org_url}. "
            "Expected format: https://dev.azure.com/{{org}} or https://{{org}}.visualstudio.com"
        )
    org = match.group(1)
    return f"https://vsrm.dev.azure.com/{org}"


def _api(method: str, url: str, params: dict | None = None, json_body: dict | None = None) -> dict:
    """Make an authenticated Azure DevOps Release Management API call with retry for 429/5xx."""
    import time

    headers = get_auth_header()
    headers["Content-Type"] = "application/json"
    base_params = {"api-version": "7.1"}
    if params:
        base_params.update(params)

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
            return resp.json()
    raise RuntimeError(f"Azure DevOps API request failed after {max_retries} retries")


def list_release_definitions(project: str, top: int = 50) -> list[dict]:
    """List all classic release definitions in a project."""
    rm_url = _get_rm_url()
    url = f"{rm_url}/{project}/_apis/release/definitions"
    data = _api("GET", url, params={"$top": top})

    return [
        {
            "id": d.get("id"),
            "name": d.get("name"),
            "path": d.get("path"),
            "description": d.get("description"),
            "created_by": _format_identity(d.get("createdBy")),
            "created_on": d.get("createdOn"),
            "url": d.get("url"),
        }
        for d in data.get("value", [])
    ]


def list_releases(project: str, definition_id: int | None = None, top: int = 25) -> list[dict]:
    """List releases, optionally filtered by release definition."""
    rm_url = _get_rm_url()
    url = f"{rm_url}/{project}/_apis/release/releases"

    params = {"$top": top}
    if definition_id:
        params["definitionId"] = definition_id

    data = _api("GET", url, params=params)

    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "status": r.get("status"),
            "reason": r.get("reason"),
            "description": r.get("description"),
            "created_on": r.get("createdOn"),
            "created_by": _format_identity(r.get("createdBy")),
            "release_definition": {
                "id": r.get("releaseDefinition", {}).get("id"),
                "name": r.get("releaseDefinition", {}).get("name"),
            },
        }
        for r in data.get("value", [])
    ]


def get_release(project: str, release_id: int) -> dict:
    """Get detailed information about a specific release, including environment status."""
    rm_url = _get_rm_url()
    url = f"{rm_url}/{project}/_apis/release/releases/{release_id}"
    r = _api("GET", url)

    environments = [
        {
            "id": env.get("id"),
            "name": env.get("name"),
            "status": env.get("status"),
            "deploy_steps": [
                {
                    "id": step.get("id"),
                    "status": step.get("status"),
                    "reason": step.get("reason"),
                    "last_modified_on": step.get("lastModifiedOn"),
                }
                for step in env.get("deploySteps", [])
            ],
        }
        for env in r.get("environments", [])
    ]

    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "status": r.get("status"),
        "reason": r.get("reason"),
        "description": r.get("description"),
        "created_on": r.get("createdOn"),
        "created_by": _format_identity(r.get("createdBy")),
        "release_definition": {
            "id": r.get("releaseDefinition", {}).get("id"),
            "name": r.get("releaseDefinition", {}).get("name"),
        },
        "environments": environments,
        "artifacts": [
            {
                "source_id": a.get("sourceId"),
                "type": a.get("type"),
                "alias": a.get("alias"),
            }
            for a in r.get("artifacts", [])
        ],
    }


def create_release(
    project: str,
    definition_id: int,
    description: str = "",
    artifacts: list[dict] | None = None,
) -> dict:
    """Create (trigger) a new release from a release definition.

    Args:
        project: Azure DevOps project name.
        definition_id: The release definition ID to create a release from.
        description: Optional description for the release.
        artifacts: Optional list of artifact version overrides. Each dict should have:
                   - alias (str): artifact source alias
                   - version_id (str): specific version/build ID
                   - version_name (str): display name for the version
    """
    rm_url = _get_rm_url()
    url = f"{rm_url}/{project}/_apis/release/releases"

    body: dict = {
        "definitionId": definition_id,
        "description": description or "",
    }

    if artifacts:
        body["artifacts"] = [
            {
                "alias": a["alias"],
                "instanceReference": {
                    "id": a.get("version_id", ""),
                    "name": a.get("version_name", ""),
                },
            }
            for a in artifacts
        ]

    r = _api("POST", url, json_body=body)

    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "status": r.get("status"),
        "created_on": r.get("createdOn"),
        "created_by": _format_identity(r.get("createdBy")),
        "release_definition": {
            "id": r.get("releaseDefinition", {}).get("id"),
            "name": r.get("releaseDefinition", {}).get("name"),
        },
    }


def list_release_approvals(
    project: str,
    status: str = "pending",
    top: int = 25,
    assigned_to: str = "",
) -> list[dict]:
    """List release approvals, optionally filtered by status.

    Args:
        project: Azure DevOps project name.
        status: Filter by status: "pending", "approved", "rejected", "reassigned",
                "canceled", "skipped", "undefined". Default is "pending".
        top: Maximum number of approvals to return.
        assigned_to: Optional filter by approver display name or unique name.
    """
    rm_url = _get_rm_url()
    url = f"{rm_url}/{project}/_apis/release/approvals"
    params: dict = {"statusFilter": status, "$top": top}
    if assigned_to:
        params["assignedToFilter"] = assigned_to

    data = _api("GET", url, params=params)
    return [
        {
            "id": a.get("id"),
            "status": a.get("status"),
            "is_automated": a.get("isAutomated"),
            "created_on": a.get("createdOn"),
            "modified_on": a.get("modifiedOn"),
            "assigned_to": _format_identity(a.get("approver")),
            "release": {
                "id": a.get("release", {}).get("id"),
                "name": a.get("release", {}).get("name"),
            },
            "release_definition": {
                "id": a.get("releaseDefinition", {}).get("id"),
                "name": a.get("releaseDefinition", {}).get("name"),
            },
            "release_environment": {
                "id": a.get("releaseEnvironment", {}).get("id"),
                "name": a.get("releaseEnvironment", {}).get("name"),
            },
        }
        for a in data.get("value", [])
    ]


def update_release_approval(
    project: str,
    approval_id: int,
    status: str,
    comments: str = "",
) -> dict:
    """Approve or reject a release approval.

    Args:
        project: Azure DevOps project name.
        approval_id: The approval ID.
        status: "approved" or "rejected".
        comments: Optional comments for the approval decision.
    """
    rm_url = _get_rm_url()
    url = f"{rm_url}/{project}/_apis/release/approvals/{approval_id}"

    body: dict = {"status": status}
    if comments:
        body["comments"] = comments

    a = _api("PATCH", url, json_body=body)
    return {
        "id": a.get("id"),
        "status": a.get("status"),
        "comments": a.get("comments"),
        "modified_on": a.get("modifiedOn"),
        "assigned_to": _format_identity(a.get("approver")),
        "release": {
            "id": a.get("release", {}).get("id"),
            "name": a.get("release", {}).get("name"),
        },
    }


def _format_identity(identity) -> str | None:
    """Format an identity reference to a readable string."""
    if identity is None:
        return None
    if isinstance(identity, dict):
        return identity.get("displayName") or identity.get("uniqueName")
    return str(identity)
