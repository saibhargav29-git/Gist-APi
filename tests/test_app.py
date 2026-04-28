"""
test_app.py
-----------
Tests for both the core GitHub client logic and the HTTP routing layer.

Structure:
  TestGitHubClient   — unit tests for github_client.py in isolation
                       (all HTTP calls to GitHub are mocked)
  TestUserGistsRoute — integration-style tests for the Flask routes
                       (github_client is mocked; Flask test client used)

"""

import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout

from github_client import get_public_gists, GitHubUserNotFoundError, GitHubAPIError
from app import app


# ---------------------------------------------------------------------------
# Shared fixtures and sample data
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Flask test client — makes HTTP requests in-process, no real port."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_gist(gid: str, description: str = "A gist", files: list[str] | None = None):
    """Build a minimal GitHub gist dict for use in tests."""
    return {
        "id": gid,
        "description": description,
        "html_url": f"https://gist.github.com/octocat/{gid}",
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2021-06-15T10:00:00Z",
        "files": {f: {} for f in (files or ["file.py"])},
        "comments": 0,
    }


SAMPLE_GISTS = [
    _make_gist("abc123", "Hello World", ["hello.py", "readme.md"]),
    _make_gist("def456", "", ["script.sh"]),   # empty description edge case
]


# ---------------------------------------------------------------------------
# TestGitHubClient — tests for github_client.py core logic
# ---------------------------------------------------------------------------

class TestGitHubClient:
    """Unit tests for get_public_gists() — all GitHub HTTP calls are mocked."""

    def _mock_response(self, json_data: list, status_code: int = 200) -> MagicMock:
        mock = MagicMock()
        mock.status_code = status_code
        mock.ok = status_code == 200
        mock.json.return_value = json_data
        return mock

    
    def test_returns_gists_for_valid_user(self):
        with patch("github_client.requests.get", return_value=self._mock_response(SAMPLE_GISTS)):
            result = get_public_gists("octocat")
        assert len(result) == 2
        assert result[0]["id"] == "abc123"

    
    def test_raises_user_not_found_on_404(self):
        with patch("github_client.requests.get", return_value=self._mock_response([], 404)):
            with pytest.raises(GitHubUserNotFoundError) as exc_info:
                get_public_gists("nonexistent-user-xyz")
        assert "nonexistent-user-xyz" in str(exc_info.value)

    
    def test_raises_api_error_on_unexpected_status(self):
        with patch("github_client.requests.get", return_value=self._mock_response([], 500)):
            with pytest.raises(GitHubAPIError):
                get_public_gists("someuser")

    
    def test_returns_empty_list_for_user_with_no_gists(self):
        with patch("github_client.requests.get", return_value=self._mock_response([])):
            result = get_public_gists("empty-user")
        assert result == []

    
    def test_pagination_fetches_all_pages(self):
        """
        WHY this test matters:
        GitHub caps results at per_page (default 30, max 100).
        Without pagination, a user with 31+ gists silently loses data.
        We verify the client keeps fetching until it gets an empty page.
        """
        page_1 = [_make_gist(f"gist-{i}") for i in range(3)]
        page_2 = [_make_gist(f"gist-{i}") for i in range(3, 5)]
        page_3 = []  # signals end of results

        mock_responses = [
            self._mock_response(page_1),
            self._mock_response(page_2),
            self._mock_response(page_3),
        ]

        with patch("github_client.requests.get", side_effect=mock_responses):
            result = get_public_gists("octocat", per_page=3)

        assert len(result) == 5
        assert result[0]["id"] == "gist-0"
        assert result[4]["id"] == "gist-4"

    
    def test_pagination_stops_when_partial_page_returned(self):
        """
        If GitHub returns fewer items than per_page, it's the last page.
        We should NOT make an extra request.
        """
        page_1 = [_make_gist(f"g-{i}") for i in range(3)]
        # per_page=5, got 3 → last page, no further requests needed

        with patch("github_client.requests.get", return_value=self._mock_response(page_1)) as mock_get:
            result = get_public_gists("octocat", per_page=5)

        assert len(result) == 3
        assert mock_get.call_count == 1  # only one request made

    
    def test_raises_api_error_on_timeout(self):
        """
        A slow GitHub response hangs the worker
        process and produces a raw 500 instead of a clean 502.
        We verify Timeout is caught and re-raised as GitHubAPIError.
        """
        with patch("github_client.requests.get", side_effect=Timeout()):
            with pytest.raises(GitHubAPIError) as exc_info:
                get_public_gists("octocat")
        assert "timed out" in str(exc_info.value)



# ---------------------------------------------------------------------------
# TestUserGistsRoute — tests for the Flask HTTP routes
# ---------------------------------------------------------------------------

class TestUserGistsRoute:
    """Integration tests for GET /<username> — github_client is mocked."""

    
    def test_returns_200_and_correct_shape_for_valid_user(self, client):
        with patch("app.get_public_gists", return_value=SAMPLE_GISTS):
            response = client.get("/octocat")

        assert response.status_code == 200
        data = response.get_json()
        assert data["username"] == "octocat"
        assert data["gist_count"] == 2
        assert len(data["gists"]) == 2

    
    def test_each_gist_has_expected_fields(self, client):
        with patch("app.get_public_gists", return_value=SAMPLE_GISTS):
            response = client.get("/octocat")

        gist = response.get_json()["gists"][0]
        for field in ("id", "description", "url", "created_at", "updated_at", "files", "comments"):
            assert field in gist, f"Missing field: {field}"

    
    def test_files_returned_as_list_of_filenames(self, client):
        with patch("app.get_public_gists", return_value=SAMPLE_GISTS):
            response = client.get("/octocat")

        files = response.get_json()["gists"][0]["files"]
        assert isinstance(files, list)
        assert set(files) == {"hello.py", "readme.md"}

    
    def test_empty_description_replaced_with_placeholder(self, client):
        with patch("app.get_public_gists", return_value=SAMPLE_GISTS):
            response = client.get("/octocat")

        gists = response.get_json()["gists"]
        empty_desc_gist = next(g for g in gists if g["id"] == "def456")
        assert empty_desc_gist["description"] == "(no description)"

    
    def test_returns_200_with_empty_list_for_user_with_no_gists(self, client):
        with patch("app.get_public_gists", return_value=[]):
            response = client.get("/zero-gists-user")

        assert response.status_code == 200
        data = response.get_json()
        assert data["gist_count"] == 0
        assert data["gists"] == []

    
    def test_returns_404_for_nonexistent_github_user(self, client):
        with patch("app.get_public_gists", side_effect=GitHubUserNotFoundError("not found")):
            response = client.get("/ghost-user-xyz")

        assert response.status_code == 404
        assert "error" in response.get_json()

    
    def test_returns_502_when_github_api_fails(self, client):
        with patch("app.get_public_gists", side_effect=GitHubAPIError("GitHub 500")):
            response = client.get("/anyuser")

        assert response.status_code == 502
        assert "error" in response.get_json()
    
    def test_logs_warning_when_github_response_missing_expected_field(self, client):
        """
        GIVEN GitHub's response is missing an expected field (e.g. after a schema change)
        WHEN  GET /<username> is called
        THEN  a warning is logged so the issue doesn't go silently unnoticed,
              AND the response still returns 200 (non-critical failure)
        """
        gist_missing_url = _make_gist("xyz789")
        del gist_missing_url["html_url"]  # simulate GitHub renaming this field

        with patch("app.get_public_gists", return_value=[gist_missing_url]):
            with patch("app.logger") as mock_logger:
                response = client.get("/octocat")

        assert response.status_code == 200
        mock_logger.warning.assert_called_once()
        assert response.get_json()["gists"][0]["url"] is None

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "healthy"}    
