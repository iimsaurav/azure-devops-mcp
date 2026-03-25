"""Board and work item operations for Azure DevOps — REST API only."""

import os

import httpx

from azure_devops_mcp.auth import get_auth_header


def _get_org_url() -> str:
    url = os.getenv("AZURE_DEVOPS_ORG_URL")
    if not url:
        raise ValueError("AZURE_DEVOPS_ORG_URL is not set.")
    return url.rstrip("/")


def _api(method: str, url: str, params: dict | None = None, json_body: dict | list | None = None,
         content_type: str = "application/json") -> dict | list:
    """Make an authenticated Azure DevOps REST API call with retry for 429/5xx."""
    import time

    headers = get_auth_header()
    headers["Content-Type"] = content_type
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
            if resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
            return {"text": resp.text}
    raise RuntimeError(f"Azure DevOps API request failed after {max_retries} retries")


def list_boards(project: str, team: str | None = None) -> list[dict]:
    """List all boards for a project/team."""
    org_url = _get_org_url()
    team_segment = f"{project}/{team}" if team else project
    url = f"{org_url}/{team_segment}/_apis/work/boards"
    data = _api("GET", url)
    return [
        {
            "id": b.get("id"),
            "name": b.get("name"),
            "url": b.get("url"),
        }
        for b in data.get("value", [])
    ]


def get_board_columns(project: str, board: str, team: str | None = None) -> list[dict]:
    """Get columns for a specific board."""
    org_url = _get_org_url()
    team_segment = f"{project}/{team}" if team else project
    url = f"{org_url}/{team_segment}/_apis/work/boards/{board}/columns"
    data = _api("GET", url)
    return [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "item_limit": c.get("itemLimit"),
            "state_mappings": c.get("stateMappings"),
            "column_type": c.get("columnType"),
        }
        for c in data.get("value", [])
    ]


def get_board_work_items(project: str, board: str, team: str | None = None) -> dict:
    """Get work items on a specific board along with board columns."""
    org_url = _get_org_url()

    # Fetch board columns
    columns = get_board_columns(project, board, team)

    # Fetch board definition
    team_segment = f"{project}/{team}" if team else project
    url = f"{org_url}/{team_segment}/_apis/work/boards/{board}"
    board_data = _api("GET", url)

    # Query work items via WIQL
    # Escape single quotes in project name to prevent WIQL injection
    safe_project = project.replace("'", "''")
    wiql = (
        f"SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType], "
        f"[System.AssignedTo], [System.AreaPath], [System.IterationPath] "
        f"FROM workitems "
        f"WHERE [System.TeamProject] = '{safe_project}' "
        f"AND [System.State] <> 'Removed' "
        f"ORDER BY [System.ChangedDate] DESC"
    )
    items = _query_and_fetch(project, wiql, top=200, fields=[
        "System.Id", "System.Title", "System.State", "System.WorkItemType",
        "System.AssignedTo", "System.AreaPath", "System.IterationPath",
        "System.CreatedDate", "System.ChangedDate",
    ])

    return {
        "board": board_data.get("name"),
        "columns": columns,
        "work_items": items,
    }


def get_work_item(project: str, work_item_id: int) -> dict:
    """Get detailed information about a work item."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}"
    data = _api("GET", url, params={"$expand": "All"})

    fields = data.get("fields", {})
    relations = data.get("relations", [])
    return {
        "id": data.get("id"),
        "rev": data.get("rev"),
        "url": data.get("url"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "type": fields.get("System.WorkItemType"),
        "assigned_to": _format_identity(fields.get("System.AssignedTo")),
        "area_path": fields.get("System.AreaPath"),
        "iteration_path": fields.get("System.IterationPath"),
        "description": fields.get("System.Description"),
        "acceptance_criteria": fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"),
        "priority": fields.get("Microsoft.VSTS.Common.Priority"),
        "severity": fields.get("Microsoft.VSTS.Common.Severity"),
        "story_points": fields.get("Microsoft.VSTS.Scheduling.StoryPoints"),
        "remaining_work": fields.get("Microsoft.VSTS.Scheduling.RemainingWork"),
        "original_estimate": fields.get("Microsoft.VSTS.Scheduling.OriginalEstimate"),
        "created_date": fields.get("System.CreatedDate"),
        "created_by": _format_identity(fields.get("System.CreatedBy")),
        "changed_date": fields.get("System.ChangedDate"),
        "changed_by": _format_identity(fields.get("System.ChangedBy")),
        "tags": fields.get("System.Tags"),
        "relations": [
            {"rel": r.get("rel"), "url": r.get("url"), "attributes": r.get("attributes")}
            for r in (relations or [])
        ],
    }


def create_work_item(
    project: str,
    work_item_type: str,
    title: str,
    description: str = "",
    assigned_to: str = "",
    area_path: str = "",
    iteration_path: str = "",
    priority: int | None = None,
    tags: str = "",
    additional_fields: dict | None = None,
    parent_id: int | None = None,
) -> dict:
    """Create a new work item."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/workitems/${work_item_type}"

    document = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
    ]
    if description:
        document.append({"op": "add", "path": "/fields/System.Description", "value": description})
    if assigned_to:
        document.append({"op": "add", "path": "/fields/System.AssignedTo", "value": assigned_to})
    if area_path:
        document.append({"op": "add", "path": "/fields/System.AreaPath", "value": area_path})
    if iteration_path:
        document.append({"op": "add", "path": "/fields/System.IterationPath", "value": iteration_path})
    if priority is not None:
        document.append({"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": priority})
    if tags:
        document.append({"op": "add", "path": "/fields/System.Tags", "value": tags})
    if additional_fields:
        for field_path, value in additional_fields.items():
            path = field_path if field_path.startswith("/fields/") else f"/fields/{field_path}"
            document.append({"op": "add", "path": path, "value": value})
    if parent_id is not None:
        rel = _resolve_relation_type("parent")
        parent_url = f"{org_url}/{project}/_apis/wit/workItems/{parent_id}"
        document.append({"op": "add", "path": "/relations/-", "value": {
            "rel": rel, "url": parent_url, "attributes": {},
        }})

    data = _api("POST", url, json_body=document, content_type="application/json-patch+json")
    fields = data.get("fields", {})
    return {
        "id": data.get("id"),
        "url": data.get("url"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "type": fields.get("System.WorkItemType"),
    }


def update_work_item(
    project: str,
    work_item_id: int,
    fields: dict | None = None,
    add_links: list[dict] | None = None,
) -> dict:
    """Update an existing work item's fields and/or add relation links."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}"

    document = []
    if fields:
        for field_name, value in fields.items():
            path = field_name if field_name.startswith("/fields/") else f"/fields/{field_name}"
            document.append({"op": "replace", "path": path, "value": value})

    if add_links:
        for link in add_links:
            rel = _resolve_relation_type(link["link_type"])
            target_url = f"{org_url}/{project}/_apis/wit/workItems/{link['target_id']}"
            link_value: dict = {"rel": rel, "url": target_url, "attributes": {}}
            if link.get("comment"):
                link_value["attributes"]["comment"] = link["comment"]
            document.append({"op": "add", "path": "/relations/-", "value": link_value})

    data = _api("PATCH", url, json_body=document, content_type="application/json-patch+json")
    fields_out = data.get("fields", {})
    return {
        "id": data.get("id"),
        "url": data.get("url"),
        "title": fields_out.get("System.Title"),
        "state": fields_out.get("System.State"),
        "type": fields_out.get("System.WorkItemType"),
        "changed_date": fields_out.get("System.ChangedDate"),
        "relations": [
            {"rel": r.get("rel"), "url": r.get("url"), "attributes": r.get("attributes")}
            for r in (data.get("relations") or [])
        ],
    }


# Map of friendly relation names to Azure DevOps relation type reference names
_RELATION_TYPES: dict[str, str] = {
    "parent": "System.LinkTypes.Hierarchy-Reverse",
    "child": "System.LinkTypes.Hierarchy-Forward",
    "related": "System.LinkTypes.Related",
    "predecessor": "System.LinkTypes.Dependency-Reverse",
    "successor": "System.LinkTypes.Dependency-Forward",
}


def _resolve_relation_type(link_type: str) -> str:
    """Resolve a friendly relation name or pass through a fully-qualified type."""
    return _RELATION_TYPES.get(link_type.lower(), link_type)


def query_work_items(project: str, wiql_query: str) -> list[dict]:
    """Execute a WIQL query and return work item details."""
    return _query_and_fetch(project, wiql_query, top=200, fields=[
        "System.Id", "System.Title", "System.State", "System.WorkItemType",
        "System.AssignedTo", "System.AreaPath", "System.IterationPath",
        "System.Tags", "System.CreatedDate", "System.ChangedDate",
        "Microsoft.VSTS.Common.Priority",
    ])


def _query_and_fetch(project: str, wiql: str, top: int = 200, fields: list[str] | None = None) -> list[dict]:
    """Run a WIQL query and batch-fetch the resulting work items."""
    org_url = _get_org_url()

    # Execute WIQL
    wiql_url = f"{org_url}/{project}/_apis/wit/wiql"
    result = _api("POST", wiql_url, params={"$top": top}, json_body={"query": wiql})

    work_item_refs = result.get("workItems", [])
    if not work_item_refs:
        return []

    ids = [wi["id"] for wi in work_item_refs[:200]]

    # Batch fetch work items
    ids_str = ",".join(str(i) for i in ids)
    items_url = f"{org_url}/{project}/_apis/wit/workitems"
    fetch_params = {"ids": ids_str}
    if fields:
        fetch_params["fields"] = ",".join(fields)

    data = _api("GET", items_url, params=fetch_params)

    return [
        {
            "id": wi.get("id"),
            "title": wi.get("fields", {}).get("System.Title"),
            "state": wi.get("fields", {}).get("System.State"),
            "type": wi.get("fields", {}).get("System.WorkItemType"),
            "assigned_to": _format_identity(wi.get("fields", {}).get("System.AssignedTo")),
            "area_path": wi.get("fields", {}).get("System.AreaPath"),
            "iteration_path": wi.get("fields", {}).get("System.IterationPath"),
            "priority": wi.get("fields", {}).get("Microsoft.VSTS.Common.Priority"),
            "tags": wi.get("fields", {}).get("System.Tags"),
            "created_date": wi.get("fields", {}).get("System.CreatedDate"),
            "changed_date": wi.get("fields", {}).get("System.ChangedDate"),
        }
        for wi in data.get("value", [])
    ]


def get_work_item_comments(project: str, work_item_id: int, top: int = 50) -> list[dict]:
    """Get comments on a work item.

    Args:
        project: Azure DevOps project name.
        work_item_id: The work item ID.
        top: Maximum number of comments to return.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}/comments"
    data = _api("GET", url, params={"$top": top})
    return [
        {
            "id": c.get("id"),
            "text": c.get("text"),
            "version": c.get("version"),
            "created_by": _format_identity(c.get("createdBy")),
            "created_date": c.get("createdDate"),
            "modified_by": _format_identity(c.get("modifiedBy")),
            "modified_date": c.get("modifiedDate"),
        }
        for c in data.get("comments", [])
    ]


def add_work_item_comment(project: str, work_item_id: int, text: str) -> dict:
    """Add a comment to a work item.

    Args:
        project: Azure DevOps project name.
        work_item_id: The work item ID.
        text: The comment text (supports HTML).
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}/comments"
    data = _api("POST", url, json_body={"text": text})
    return {
        "id": data.get("id"),
        "text": data.get("text"),
        "created_by": _format_identity(data.get("createdBy")),
        "created_date": data.get("createdDate"),
    }


def delete_work_item(project: str, work_item_id: int, destroy: bool = False) -> dict:
    """Delete a work item (move to recycle bin, or permanently destroy).

    Args:
        project: Azure DevOps project name.
        work_item_id: The work item ID to delete.
        destroy: If True, permanently delete. If False (default), move to recycle bin.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}"
    params: dict = {}
    if destroy:
        params["destroy"] = "true"
    data = _api("DELETE", url, params=params)
    if isinstance(data, dict):
        return {
            "id": data.get("id"),
            "code": data.get("code"),
            "message": data.get("message", "Work item deleted"),
        }
    return {"id": work_item_id, "message": "Work item deleted"}


def list_saved_queries(project: str, depth: int = 2) -> list[dict]:
    """List saved work item queries (folders and queries).

    Args:
        project: Azure DevOps project name.
        depth: How deep to recurse into query folders (default: 2).
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/queries"
    data = _api("GET", url, params={"$depth": depth, "$expand": "minimal"})

    def _flatten_queries(node: dict) -> list[dict]:
        result = []
        if node.get("isFolder"):
            result.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "path": node.get("path"),
                "is_folder": True,
            })
            for child in node.get("children", []):
                result.extend(_flatten_queries(child))
        else:
            result.append({
                "id": node.get("id"),
                "name": node.get("name"),
                "path": node.get("path"),
                "is_folder": False,
                "query_type": node.get("queryType"),
            })
        return result

    results = []
    if data.get("isFolder"):
        for child in data.get("children", []):
            results.extend(_flatten_queries(child))
    else:
        results.extend(_flatten_queries(data))
    return results


def run_saved_query(project: str, query_id: str) -> list[dict]:
    """Execute a saved query by its ID and return work item details.

    Args:
        project: Azure DevOps project name.
        query_id: The saved query GUID.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wit/wiql/{query_id}"
    result = _api("GET", url)

    work_item_refs = result.get("workItems", [])
    if not work_item_refs:
        return []

    ids = [wi["id"] for wi in work_item_refs[:200]]
    ids_str = ",".join(str(i) for i in ids)
    items_url = f"{org_url}/{project}/_apis/wit/workitems"
    fetch_params = {
        "ids": ids_str,
        "fields": "System.Id,System.Title,System.State,System.WorkItemType,"
                  "System.AssignedTo,System.AreaPath,System.IterationPath,"
                  "System.Tags,System.CreatedDate,System.ChangedDate,"
                  "Microsoft.VSTS.Common.Priority",
    }
    data = _api("GET", items_url, params=fetch_params)

    return [
        {
            "id": wi.get("id"),
            "title": wi.get("fields", {}).get("System.Title"),
            "state": wi.get("fields", {}).get("System.State"),
            "type": wi.get("fields", {}).get("System.WorkItemType"),
            "assigned_to": _format_identity(wi.get("fields", {}).get("System.AssignedTo")),
            "area_path": wi.get("fields", {}).get("System.AreaPath"),
            "iteration_path": wi.get("fields", {}).get("System.IterationPath"),
            "priority": wi.get("fields", {}).get("Microsoft.VSTS.Common.Priority"),
            "tags": wi.get("fields", {}).get("System.Tags"),
            "created_date": wi.get("fields", {}).get("System.CreatedDate"),
            "changed_date": wi.get("fields", {}).get("System.ChangedDate"),
        }
        for wi in data.get("value", [])
    ]


def _format_identity(identity) -> str | None:
    """Format an identity reference to a readable string."""
    if identity is None:
        return None
    if isinstance(identity, dict):
        return identity.get("displayName") or identity.get("uniqueName")
    return str(identity)
