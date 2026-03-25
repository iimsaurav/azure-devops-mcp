"""Tests for client modules — response shaping and URL construction."""

from unittest.mock import patch, MagicMock

import pytest


class TestPipelinesClient:
    """Test pipelines client response shaping."""

    @patch("azure_devops_mcp.clients.pipelines._api")
    @patch("azure_devops_mcp.clients.pipelines._get_org_url", return_value="https://dev.azure.com/myorg")
    def test_list_pipelines_shapes_response(self, mock_url, mock_api):
        mock_api.return_value = {
            "value": [
                {
                    "id": 1,
                    "name": "Build Pipeline",
                    "folder": "\\",
                    "revision": 5,
                    "url": "https://dev.azure.com/myorg/proj/_apis/pipelines/1",
                    "extra_field": "should_be_dropped",
                }
            ]
        }
        from azure_devops_mcp.clients.pipelines import list_pipelines
        result = list_pipelines("MyProject")

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Build Pipeline"
        assert result[0]["folder"] == "\\"
        assert "extra_field" not in result[0]

    @patch("azure_devops_mcp.clients.pipelines._api")
    @patch("azure_devops_mcp.clients.pipelines._get_org_url", return_value="https://dev.azure.com/myorg")
    def test_list_pipelines_empty(self, mock_url, mock_api):
        mock_api.return_value = {"value": []}
        from azure_devops_mcp.clients.pipelines import list_pipelines
        result = list_pipelines("MyProject")
        assert result == []

    @patch("azure_devops_mcp.clients.pipelines._api")
    @patch("azure_devops_mcp.clients.pipelines._get_org_url", return_value="https://dev.azure.com/myorg")
    def test_trigger_pipeline_shapes_response(self, mock_url, mock_api):
        mock_api.return_value = {
            "id": 42,
            "name": "20230101.1",
            "state": "inProgress",
            "createdDate": "2023-01-01T00:00:00Z",
            "url": "https://dev.azure.com/myorg/proj/_apis/pipelines/1/runs/42",
            "pipeline": {"id": 1, "name": "Build Pipeline"},
        }
        from azure_devops_mcp.clients.pipelines import trigger_pipeline
        result = trigger_pipeline("MyProject", 1, {"env": "prod"})

        assert result["id"] == 42
        assert result["state"] == "inProgress"
        assert result["pipeline_id"] == 1
        assert result["pipeline_name"] == "Build Pipeline"


class TestReleasesClient:
    """Test releases client URL construction."""

    def test_get_rm_url_extracts_org(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_ORG_URL", "https://dev.azure.com/myorganization")
        from azure_devops_mcp.clients.releases import _get_rm_url
        assert _get_rm_url() == "https://vsrm.dev.azure.com/myorganization"

    def test_get_rm_url_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_ORG_URL", "https://dev.azure.com/myorg/")
        from azure_devops_mcp.clients.releases import _get_rm_url
        assert _get_rm_url() == "https://vsrm.dev.azure.com/myorg"

    def test_get_rm_url_raises_on_bad_format(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_ORG_URL", "https://other.example.com/org")
        from azure_devops_mcp.clients.releases import _get_rm_url
        with pytest.raises(ValueError, match="Cannot extract organization"):
            _get_rm_url()

    def test_get_rm_url_raises_when_unset(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_ORG_URL", raising=False)
        from azure_devops_mcp.clients.releases import _get_rm_url
        with pytest.raises(ValueError, match="AZURE_DEVOPS_ORG_URL is not set"):
            _get_rm_url()


class TestGitClient:
    """Test git client response shaping."""

    @patch("azure_devops_mcp.clients.git._api")
    @patch("azure_devops_mcp.clients.git._get_org_url", return_value="https://dev.azure.com/myorg")
    def test_list_branches_strips_refs_prefix(self, mock_url, mock_api):
        mock_api.return_value = {
            "value": [
                {"name": "refs/heads/main", "objectId": "abc123", "creator": None},
                {"name": "refs/heads/feature/foo", "objectId": "def456", "creator": None},
            ]
        }
        from azure_devops_mcp.clients.git import list_branches
        result = list_branches("MyProject", "my-repo")

        assert result[0]["name"] == "main"
        assert result[1]["name"] == "feature/foo"

    @patch("azure_devops_mcp.clients.git._api")
    @patch("azure_devops_mcp.clients.git._get_org_url", return_value="https://dev.azure.com/myorg")
    def test_compare_branches_caps_changes(self, mock_url, mock_api):
        """Verify that changes are capped at 100."""
        changes = [{"changeType": "edit", "item": {"path": f"/file{i}.py", "isFolder": False}} for i in range(150)]
        mock_api.return_value = {
            "aheadCount": 5,
            "behindCount": 2,
            "commonCommit": "abc",
            "changes": changes,
        }
        from azure_devops_mcp.clients.git import compare_branches
        result = compare_branches("MyProject", "repo", "main", "develop")

        assert result["change_count"] == 150  # actual count
        assert len(result["changes"]) == 100  # capped at 100

    def test_format_pull_request_strips_refs(self):
        from azure_devops_mcp.clients.git import _format_pull_request
        pr = {
            "pullRequestId": 42,
            "title": "Add feature",
            "description": "Some desc",
            "status": "active",
            "isDraft": False,
            "sourceRefName": "refs/heads/feature/bar",
            "targetRefName": "refs/heads/main",
            "createdBy": {"displayName": "John Doe"},
            "creationDate": "2023-01-01",
            "mergeStatus": "succeeded",
            "mergeId": "m-1",
            "reviewers": [],
            "url": "https://url",
            "repository": {"id": "r1", "name": "my-repo"},
        }
        result = _format_pull_request(pr)
        assert result["id"] == 42
        assert result["source_branch"] == "feature/bar"
        assert result["target_branch"] == "main"
        assert result["created_by"] == "John Doe"


class TestBoardsClient:
    """Test boards client relation resolution."""

    def test_resolve_relation_type_parent(self):
        from azure_devops_mcp.clients.boards import _resolve_relation_type
        assert _resolve_relation_type("parent") == "System.LinkTypes.Hierarchy-Reverse"

    def test_resolve_relation_type_child(self):
        from azure_devops_mcp.clients.boards import _resolve_relation_type
        assert _resolve_relation_type("child") == "System.LinkTypes.Hierarchy-Forward"

    def test_resolve_relation_type_related(self):
        from azure_devops_mcp.clients.boards import _resolve_relation_type
        assert _resolve_relation_type("related") == "System.LinkTypes.Related"

    def test_resolve_relation_type_passthrough(self):
        """Unknown types should be passed through as-is."""
        from azure_devops_mcp.clients.boards import _resolve_relation_type
        custom = "System.LinkTypes.Custom-Forward"
        assert _resolve_relation_type(custom) == custom

    def test_resolve_relation_type_case_insensitive(self):
        from azure_devops_mcp.clients.boards import _resolve_relation_type
        assert _resolve_relation_type("Parent") == "System.LinkTypes.Hierarchy-Reverse"
        assert _resolve_relation_type("CHILD") == "System.LinkTypes.Hierarchy-Forward"


class TestOrgUrlHelper:
    """Test _get_org_url across multiple clients."""

    def test_pipelines_get_org_url(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_ORG_URL", "https://dev.azure.com/myorg/")
        from azure_devops_mcp.clients.pipelines import _get_org_url
        assert _get_org_url() == "https://dev.azure.com/myorg"

    def test_pipelines_get_org_url_raises(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_ORG_URL", raising=False)
        from azure_devops_mcp.clients.pipelines import _get_org_url
        with pytest.raises(ValueError, match="AZURE_DEVOPS_ORG_URL is not set"):
            _get_org_url()


class TestIdentityFormatting:
    """Test _format_identity helper across clients."""

    def test_format_dict_with_display_name(self):
        from azure_devops_mcp.clients.git import _format_identity
        assert _format_identity({"displayName": "John Doe", "uniqueName": "john@example.com"}) == "John Doe"

    def test_format_dict_with_unique_name_only(self):
        from azure_devops_mcp.clients.git import _format_identity
        assert _format_identity({"uniqueName": "john@example.com"}) == "john@example.com"

    def test_format_none(self):
        from azure_devops_mcp.clients.git import _format_identity
        assert _format_identity(None) is None

    def test_format_string(self):
        from azure_devops_mcp.clients.git import _format_identity
        assert _format_identity("some-string") == "some-string"
