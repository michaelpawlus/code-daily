"""
Parse commit events from GitHub API responses.
"""


def parse_commit_events(events: list[dict]) -> list[dict]:
    """
    Parse commit events from GitHub API events.

    Filters for PushEvent types and extracts commit information.

    Args:
        events: List of GitHub API event dictionaries

    Returns:
        List of dicts with:
        - date: commit date (YYYY-MM-DD format)
        - repo: repository name
        - commits: list of commit objects (sha, message)
        - commit_count: number of commits in the push
    """
    commit_events = []

    for event in events:
        # Only process PushEvents
        if event.get("type") != "PushEvent":
            continue

        # Extract event details
        created_at = event.get("created_at", "")
        date = created_at[:10] if created_at else "unknown"
        repo = event.get("repo", {}).get("name", "unknown")

        # Extract commit information from payload
        payload = event.get("payload", {})
        commits = payload.get("commits", [])
        commit_count = payload.get("size", len(commits))

        # Parse commit details
        parsed_commits = []
        for commit in commits:
            parsed_commits.append({
                "sha": commit.get("sha", "")[:7],  # Short SHA
                "message": commit.get("message", "").split("\n")[0],  # First line only
            })

        commit_events.append({
            "date": date,
            "repo": repo,
            "commits": parsed_commits,
            "commit_count": commit_count,
        })

    return commit_events
