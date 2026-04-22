"""
app.py
------
Thin HTTP layer. Routes requests to the GitHub client and
maps domain errors to appropriate HTTP status codes.

All business logic lives in github_client.py — this file
only concerns itself with HTTP request/response handling.
"""

import logging
from flask import Flask, jsonify
from github_client import get_public_gists, GitHubUserNotFoundError, GitHubAPIError

app = Flask(__name__)

# WHY logging?
# If GitHub renames or removes a field, .get() returns None silently.
# Logging a warning makes that visible in server output without crashing
# the entire response — a proportionate response to a non-critical change.
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Fields we expect from GitHub's gist response.
# If any are missing, we log a warning so it doesn't go unnoticed.
EXPECTED_FIELDS = ("id", "html_url", "description", "created_at", "updated_at", "files", "comments")


def _format_gist(gist: dict) -> dict:
    """
    Return a curated subset of gist fields for the API response.
    Logs a warning if any expected GitHub fields are missing,
    which would indicate a GitHub API schema change.
    """
    missing = [f for f in EXPECTED_FIELDS if f not in gist]
    if missing:
        logger.warning(
            "GitHub response missing expected field(s): %s — possible API schema change.",
            missing
        )

    return {
        "id": gist.get("id"),
        "description": gist.get("description") or "(no description)",
        "url": gist.get("html_url"),
        "created_at": gist.get("created_at"),
        "updated_at": gist.get("updated_at"),
        "files": list(gist.get("files", {}).keys()),
        "comments": gist.get("comments", 0),
    }


@app.route("/<username>", methods=["GET"])
def user_gists(username: str):
    """
    GET /<username>
    Returns all public gists for the given GitHub user.

    200 — success
    404 — user does not exist on GitHub
    502 — upstream GitHub API error (we are a gateway; GitHub failed us)
    """
    try:
        raw_gists = get_public_gists(username)
        gists = [_format_gist(g) for g in raw_gists]
        return jsonify({"username": username, "gist_count": len(gists), "gists": gists}), 200

    except GitHubUserNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    except GitHubAPIError as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    # host="0.0.0.0" binds to all interfaces — required inside Docker
    # so the container accepts traffic from outside its network namespace.
    app.run(host="0.0.0.0", port=8080)