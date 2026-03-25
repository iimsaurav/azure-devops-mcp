"""Pipeline and build artifact operations for Azure DevOps."""

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
    timeout: int = 30,
) -> dict:
    """Make an authenticated Azure DevOps REST API call with retry for 429/5xx."""
    headers = get_auth_header()
    headers["Content-Type"] = "application/json"
    base_params = {"api-version": "7.1"}
    if params:
        base_params.update(params)

    max_retries = 3
    with httpx.Client(timeout=timeout) as client:
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


def list_pipelines(project: str) -> list[dict]:
    """List all pipelines in a project."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/pipelines"
    data = _api("GET", url)

    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "folder": p.get("folder"),
            "revision": p.get("revision"),
            "url": p.get("url"),
        }
        for p in data.get("value", [])
    ]


def get_pipeline_runs(project: str, pipeline_id: int, top: int = 10) -> list[dict]:
    """Get recent runs for a pipeline."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs"
    data = _api("GET", url, params={"$top": top})

    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "state": r.get("state"),
            "result": r.get("result"),
            "created_date": r.get("createdDate"),
            "finished_date": r.get("finishedDate"),
            "url": r.get("url"),
            "pipeline_id": r.get("pipeline", {}).get("id"),
            "pipeline_name": r.get("pipeline", {}).get("name"),
        }
        for r in data.get("value", [])
    ]


def get_pipeline_run_logs(project: str, pipeline_id: int, run_id: int) -> list[dict]:
    """Get logs for a specific pipeline run."""
    org_url = _get_org_url()
    logs_url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs/{run_id}/logs"
    logs_data = _api("GET", logs_url)

    logs = []
    for log_entry in logs_data.get("logs", []):
        log_id = log_entry.get("id")
        log_info = {
            "id": log_id,
            "created_on": log_entry.get("createdOn"),
            "last_changed_on": log_entry.get("lastChangedOn"),
            "line_count": log_entry.get("lineCount"),
            "url": log_entry.get("url"),
        }

        # Fetch individual log content
        if log_id is not None:
            try:
                detail_data = _api("GET", f"{logs_url}/{log_id}")
                log_info["content"] = detail_data.get("value", [])
            except httpx.HTTPStatusError:
                log_info["content"] = []

        logs.append(log_info)

    return logs


def trigger_pipeline(project: str, pipeline_id: int, parameters: dict | None = None) -> dict:
    """Trigger a new pipeline run."""
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs"

    body: dict = {}
    if parameters:
        body["templateParameters"] = parameters

    r = _api("POST", url, json_body=body, timeout=60)

    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "state": r.get("state"),
        "created_date": r.get("createdDate"),
        "url": r.get("url"),
        "pipeline_id": r.get("pipeline", {}).get("id"),
        "pipeline_name": r.get("pipeline", {}).get("name"),
    }


def list_build_artifacts(project: str, build_id: int) -> list[dict]:
    """List artifacts produced by a build.

    Args:
        project: Azure DevOps project name.
        build_id: The build ID.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/build/builds/{build_id}/artifacts"
    data = _api("GET", url)

    return [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "source": a.get("source"),
            "resource": {
                "type": a.get("resource", {}).get("type"),
                "url": a.get("resource", {}).get("url"),
                "download_url": a.get("resource", {}).get("downloadUrl"),
            },
        }
        for a in data.get("value", [])
    ]


def get_artifact_download_url(project: str, build_id: int, artifact_name: str) -> dict:
    """Get the download URL for a specific build artifact.

    Args:
        project: Azure DevOps project name.
        build_id: The build ID.
        artifact_name: The name of the artifact.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/build/builds/{build_id}/artifacts"
    data = _api("GET", url, params={"artifactName": artifact_name})

    resource = data.get("resource", {})
    return {
        "name": data.get("name"),
        "download_url": resource.get("downloadUrl"),
        "type": resource.get("type"),
        "url": resource.get("url"),
    }
