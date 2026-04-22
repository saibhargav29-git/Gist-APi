"""
github_client.py
----------------
Handles all communication with the GitHub REST API.

Separated from the HTTP layer so it can be tested independently
and replaced without touching the server code.
"""

import requests

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_PER_PAGE = 30  # GitHub's default; we make it explicit and overridable


class GitHubUserNotFoundError(Exception):
    """Raised when GitHub returns 404 for the requested username."""


class GitHubAPIError(Exception):
    """Raised when GitHub returns any unexpected non-2xx response."""


def get_public_gists(username: str, per_page: int = DEFAULT_PER_PAGE) -> list[dict]:
    """
    Fetch ALL public gists for a given GitHub username, following pagination.

    WHY pagination matters:
        GitHub's API returns at most 100 gists per request (default 30).
        A user like 'torvalds' may have hundreds. Without pagination
        you silently return an incomplete list — a subtle, hard-to-spot bug.

    Args:
        username:    GitHub username.
        per_page:    Results per page (max 100). Exposed for testability.

    Returns:
        A flat list of all gist dicts returned by GitHub.

    Raises:
        GitHubUserNotFoundError: if the GitHub user does not exist.
        GitHubAPIError:          for any other non-2xx GitHub response.
    """
    gists = []
    page = 1

    while True:
        url = f"{GITHUB_API_BASE}/users/{username}/gists"
        response = requests.get(
            url,
            params={"per_page": per_page, "page": page},
            timeout=10,
        )

        if response.status_code == 404:
            raise GitHubUserNotFoundError(f"GitHub user '{username}' not found.")

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub API returned {response.status_code} for user '{username}'."
            )

        page_data = response.json()

        # Empty page means we've consumed all results
        if not page_data:
            break

        gists.extend(page_data)

        # If we got fewer results than requested, this was the last page
        if len(page_data) < per_page:
            break

        page += 1

    return gists