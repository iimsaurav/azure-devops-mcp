"""Tests for server-level logic (project resolution, tool registration)."""

import pytest

from azure_devops_mcp.server import _resolve_project, mcp


class TestResolveProject:
    """Test the _resolve_project helper."""

    def test_explicit_project(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)
        assert _resolve_project("MyProject") == "MyProject"

    def test_falls_back_to_env_var(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "EnvProject")
        # Re-import to pick up new env var (DEFAULT_PROJECT is set at import time)
        from azure_devops_mcp import server
        server.DEFAULT_PROJECT = "EnvProject"
        assert _resolve_project("") == "EnvProject"
        assert _resolve_project(None) == "EnvProject"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "EnvProject")
        assert _resolve_project("ExplicitProject") == "ExplicitProject"

    def test_raises_when_no_project(self, monkeypatch):
        from azure_devops_mcp import server
        server.DEFAULT_PROJECT = ""
        with pytest.raises(ValueError, match="Project name is required"):
            _resolve_project("")

    def test_raises_when_none_and_no_default(self, monkeypatch):
        from azure_devops_mcp import server
        server.DEFAULT_PROJECT = ""
        with pytest.raises(ValueError, match="Project name is required"):
            _resolve_project(None)


class TestToolRegistration:
    """Verify that all expected tools are registered on the MCP server."""

    EXPECTED_TOOLS = [
        # Pipelines
        "list_pipelines", "get_pipeline_runs", "get_pipeline_run_logs",
        "trigger_pipeline", "list_build_artifacts", "get_artifact_download_url",
        # Releases
        "list_release_definitions", "list_releases", "get_release",
        "create_release", "list_release_approvals", "update_release_approval",
        # Boards & Work Items
        "list_boards", "get_board_work_items", "get_work_item",
        "create_work_item", "update_work_item", "query_work_items",
        "get_work_item_comments", "add_work_item_comment", "delete_work_item",
        "list_saved_queries", "run_saved_query",
        # Git
        "list_repositories", "get_repository", "list_branches",
        "get_commits", "get_file_content", "compare_branches",
        # Pull Requests
        "list_pull_requests", "get_pull_request", "create_pull_request",
        "update_pull_request", "get_pull_request_threads", "create_pull_request_comment",
        # Tests
        "list_test_runs", "get_test_run_results", "get_code_coverage",
        # Wikis
        "list_wikis", "get_wiki_page", "create_or_update_wiki_page",
    ]

    def test_all_41_tools_registered(self):
        """Verify that exactly 41 tools are registered."""
        tools = mcp._tool_manager.list_tools()
        tool_names = [t.name for t in tools]
        assert len(tool_names) == 41, f"Expected 41 tools, got {len(tool_names)}: {tool_names}"

    def test_each_expected_tool_exists(self):
        """Verify each expected tool name is registered."""
        tools = mcp._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        for expected in self.EXPECTED_TOOLS:
            assert expected in tool_names, f"Missing tool: {expected}"

    def test_no_unexpected_tools(self):
        """Verify no unexpected tools are registered."""
        tools = mcp._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        expected_set = set(self.EXPECTED_TOOLS)
        extra = tool_names - expected_set
        assert not extra, f"Unexpected tools found: {extra}"
