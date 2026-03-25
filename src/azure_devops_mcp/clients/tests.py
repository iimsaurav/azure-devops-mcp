"""Test management operations for Azure DevOps."""

import os
import time

import httpx

from azure_devops_mcp.auth import get_auth_header


def _get_org_url() -> str:
    url = os.getenv("AZURE_DEVOPS_ORG_URL")
    if not url:
        raise ValueError("AZURE_DEVOPS_ORG_URL is not set.")
    return url.rstrip("/")


def _api(method: str, url: str, params: dict | None = None, json_body: dict | None = None) -> dict | list:
    """Make an authenticated Azure DevOps REST API call with retry for 429/5xx."""
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
            if resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
            return {"text": resp.text}
    raise RuntimeError(f"Azure DevOps API request failed after {max_retries} retries")


def list_test_runs(project: str, top: int = 25, state: str = "") -> list[dict]:
    """List test runs in a project.

    Args:
        project: Azure DevOps project name.
        top: Maximum number of runs to return.
        state: Optional filter by state (e.g. "Completed", "InProgress", "Aborted").
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/test/runs"
    params: dict = {"$top": top}
    if state:
        params["state"] = state
    data = _api("GET", url, params=params)
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "state": r.get("state"),
            "started_date": r.get("startedDate"),
            "completed_date": r.get("completedDate"),
            "total_tests": r.get("totalTests"),
            "passed_tests": r.get("passedTests"),
            "failed_tests": r.get("unanalyzedTests"),
            "url": r.get("webAccessUrl"),
            "build": {
                "id": r.get("build", {}).get("id"),
                "name": r.get("build", {}).get("name"),
            } if r.get("build") else None,
            "release": {
                "id": r.get("release", {}).get("id"),
                "name": r.get("release", {}).get("name"),
            } if r.get("release") else None,
        }
        for r in data.get("value", [])
    ]


def get_test_run_results(project: str, run_id: int, top: int = 200, outcome: str = "") -> list[dict]:
    """Get test results for a specific test run.

    Args:
        project: Azure DevOps project name.
        run_id: The test run ID.
        top: Maximum number of results to return.
        outcome: Optional filter by outcome (e.g. "Passed", "Failed", "NotExecuted").
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/test/runs/{run_id}/results"
    params: dict = {"$top": top}
    if outcome:
        params["outcomes"] = outcome
    data = _api("GET", url, params=params)
    return [
        {
            "id": r.get("id"),
            "test_case_title": r.get("testCaseTitle"),
            "outcome": r.get("outcome"),
            "state": r.get("state"),
            "duration_in_ms": r.get("durationInMs"),
            "error_message": r.get("errorMessage"),
            "stack_trace": r.get("stackTrace"),
            "started_date": r.get("startedDate"),
            "completed_date": r.get("completedDate"),
            "automated_test_name": r.get("automatedTestName"),
            "automated_test_storage": r.get("automatedTestStorage"),
        }
        for r in data.get("value", [])
    ]


def get_code_coverage(project: str, build_id: int) -> dict:
    """Get code coverage summary for a build.

    Args:
        project: Azure DevOps project name.
        build_id: The build ID to get coverage for.
    """
    org_url = _get_org_url()
    url = f"{org_url}/{project}/_apis/test/codecoverage"
    params = {"buildId": build_id}
    data = _api("GET", url, params=params)

    coverage_entries = data.get("coverageData", [])
    return {
        "build_id": build_id,
        "coverage_data": [
            {
                "build_flavor": entry.get("buildFlavor"),
                "build_platform": entry.get("buildPlatform"),
                "modules": [
                    {
                        "name": m.get("name"),
                        "statistics": m.get("statistics"),
                        "block_count": m.get("blockCount"),
                        "block_data": m.get("blockData"),
                    }
                    for m in entry.get("coverageStats", entry.get("modules", []))
                ],
            }
            for entry in coverage_entries
        ],
    }
