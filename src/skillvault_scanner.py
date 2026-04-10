"""
Skillvault scanner for code-daily.

Shells out to the `skillvault` CLI to surface incomplete/planned work mentioned
in CLAUDE.md files, skill definitions, and spec documents across all indexed
projects. Each hit becomes a candidate quest.

Skillvault indexes instruction-style markdown (CLAUDE.md, skill SKILL.md, memory
files). We search it for "incomplete work" markers — things like TODO, "ready to
build", "planned", "coming soon", "not yet implemented", "stub" — and turn the
matches into quest candidates. This closes the build-vs-use gap by making
dormant specs visible in the daily workflow.

The scanner is defensive: if skillvault is not installed, the index is empty, or
the subprocess fails, it returns an empty list rather than crashing.
"""

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Incomplete-work markers to search for in the skillvault index.
# Each search is an independent FTS5 query; matches across queries are merged.
DEFAULT_MARKERS: tuple[str, ...] = (
    "TODO",
    "FIXME",
    "ready to build",
    "not yet implemented",
    "coming soon",
    "planned",
    "stub",
)

# Hard ceiling on results per marker to keep the scan bounded.
DEFAULT_LIMIT_PER_MARKER = 20

# Fallback path if skillvault is not on PATH.
FALLBACK_SKILLVAULT_BIN = Path("/home/michaelpawlus/projects/skillvault/.venv/bin/skillvault")


@dataclass
class SkillvaultFinding:
    """Represents an incomplete-work marker found in a skillvault-indexed file."""

    project: str          # e.g. "code-daily", "skill:portfolio-audit"
    file_type: str        # e.g. "claude-md", "skill", "memory"
    file_path: str        # absolute path reported by skillvault
    marker: str           # the marker that matched, e.g. "TODO"
    snippet: str          # excerpt from skillvault search result

    @property
    def source_ref(self) -> str:
        """
        Stable, unique reference for dedup.

        Format: skillvault:{file_path}:{marker}:{snippet_hash}

        Including a hash of the snippet means re-scans only collide when the
        surrounding text is byte-identical, which is the right trade-off: edits
        to the underlying file should surface as a new quest.
        """
        snippet_hash = hashlib.sha1(self.snippet.encode("utf-8")).hexdigest()[:8]
        return f"skillvault:{self.file_path}:{self.marker}:{snippet_hash}"

    @property
    def quest_title(self) -> str:
        """Build a human-readable quest title, truncated to 200 chars."""
        # Keep the snippet bit short — skillvault snippets can be long.
        excerpt = self.snippet.strip().replace("\n", " ")
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        title = f"[skillvault/{self.project}] {self.marker}: {excerpt}"
        if len(title) > 200:
            title = title[:197] + "..."
        return title


def _resolve_skillvault_bin() -> str | None:
    """Return a usable skillvault binary path, or None if unavailable."""
    found = shutil.which("skillvault")
    if found:
        return found
    if FALLBACK_SKILLVAULT_BIN.exists():
        return str(FALLBACK_SKILLVAULT_BIN)
    return None


def _run_skillvault_search(
    binary: str,
    query: str,
    limit: int,
) -> list[dict]:
    """
    Run `skillvault search QUERY --json --limit N` and return the results list.

    Returns an empty list on any failure (timeout, non-zero exit, malformed JSON).
    Errors are swallowed intentionally so a flaky external tool never breaks the
    code-daily workflow.
    """
    try:
        result = subprocess.run(
            [binary, "search", query, "--json", "--limit", str(limit)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []

    if result.returncode != 0:
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    results = payload.get("results")
    if not isinstance(results, list):
        return []
    return results


def scan_skillvault(
    markers: tuple[str, ...] = DEFAULT_MARKERS,
    limit_per_marker: int = DEFAULT_LIMIT_PER_MARKER,
) -> list[SkillvaultFinding]:
    """
    Scan the skillvault index for incomplete-work markers.

    Args:
        markers: Search terms to probe the index with.
        limit_per_marker: Max results to request per marker.

    Returns:
        List of SkillvaultFinding objects. Empty if skillvault is unavailable.
    """
    binary = _resolve_skillvault_bin()
    if binary is None:
        return []

    findings: list[SkillvaultFinding] = []
    seen_refs: set[str] = set()

    for marker in markers:
        raw_results = _run_skillvault_search(binary, marker, limit_per_marker)
        for item in raw_results:
            project = item.get("project") or ""
            file_type = item.get("file_type") or ""
            file_path = item.get("file_path") or ""
            snippet = item.get("snippet") or ""
            if not file_path or not snippet:
                continue

            finding = SkillvaultFinding(
                project=project,
                file_type=file_type,
                file_path=file_path,
                marker=marker,
                snippet=snippet,
            )
            # Dedup within a single scan (same snippet matches multiple markers).
            ref = finding.source_ref
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            findings.append(finding)

    return findings
