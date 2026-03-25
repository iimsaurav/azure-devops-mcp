"""Wiki operations for Azure DevOps."""

import os
import time

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
    raw_body: str | None = None,
    extra_headers: dict | None = None,
) -> dict | list:
    """Make an authenticated Azure DevOps REST API call with retry for 429/5xx."""
    headers = get_auth_header()
    headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)
    base_params = {"api-version": "7.1"}
    if params:
        base_params.update(params)

    max_retries = 3
    with httpx.Client(timeout=30) as client:
        for attempt in range(max_retries):
            kwargs: dict = {
                "headers": headers,
                "params": base_params,
            }
            if json_body is not None:
                kwargs["json"] = json_body
            elif raw_body is not None:
                kwargs["content"] = raw_body.encode("utf-8")
            resp = client.request(method, url, **kwargs)
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


def list_wikis(project: str) -> list[dict]:
    """List all wikis in a project."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wiki/wikis"
    data = _api("GET", url)
    return [
        {
            "id": w.get("id"),
            "name": w.get("name"),
            "type": w.get("type"),
            "url": w.get("url"),
            "versions": [
                {"version": v.get("version")}
                for v in w.get("versions", [])
            ],
        }
        for w in data.get("value", [])
    ]


def get_wiki_page(project: str, wiki_id: str, path: str = "/", include_content: bool = True) -> dict:
    """Get a wiki page by path.

    Args:
        project: Azure DevOps project name.
        wiki_id: The wiki identifier (name or ID).
        path: Page path (e.g. "/Home", "/Release Notes/v2"). Defaults to root.
        include_content: Whether to include the page markdown content.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wiki/wikis/{wiki_id}/pages"
    params: dict = {"path": path, "includeContent": str(include_content).lower()}
    data = _api("GET", url, params=params)
    return {
        "id": data.get("id"),
        "path": data.get("path"),
        "content": data.get("content"),
        "git_item_path": data.get("gitItemPath"),
        "order": data.get("order"),
        "is_parent_page": data.get("isParentPage"),
        "sub_pages": [
            {"id": sp.get("id"), "path": sp.get("path")}
            for sp in data.get("subPages", [])
        ] if data.get("subPages") else [],
    }


def create_or_update_wiki_page(
    project: str,
    wiki_id: str,
    path: str,
    content: str,
    comment: str = "",
    if_match: str = "",
) -> dict:
    """Create or update a wiki page.

    Args:
        project: Azure DevOps project name.
        wiki_id: The wiki identifier (name or ID).
        path: Page path (e.g. "/Release Notes/v3").
        content: Markdown content for the page.
        comment: Optional commit comment.
        if_match: ETag for optimistic concurrency (required for updates, empty for creates).
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/wiki/wikis/{wiki_id}/pages"
    params: dict = {"path": path}
    if comment:
        params["comment"] = comment

    extra: dict = {}
    if if_match:
        extra["If-Match"] = if_match

    data = _api("PUT", url, params=params, json_body={"content": content}, extra_headers=extra)
    return {
        "id": data.get("id"),
        "path": data.get("path"),
        "content": data.get("content"),
        "git_item_path": data.get("gitItemPath"),
    }
