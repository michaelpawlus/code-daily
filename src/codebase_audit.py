"""Write the codebase enhancement audit to the Obsidian vault.

The nightly `newsandideas` pipeline delegates the codebase audit to a
sub-agent that returns a ranked markdown list. Each bullet leads with a
`[[project-name]]` wiki-link so Obsidian's backlinks panel can answer
"show every audit that mentioned conductor."

This module:
- captures the audit body into ``Project Ideas/codebase-enhancements-{date}.md``
- extracts every ``[[name]]`` link target
- creates a one-line stub note at ``projects/{slug}.md`` for any link target
  that doesn't already have a hub — so backlinks resolve cleanly instead of
  living in the "unresolved links" panel.

All vault writes go through :mod:`src.oj_client` so frontmatter and slug
rules stay consistent with the rest of the pipeline.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from src import oj_client

_AUDIT_FOLDER = "Project Ideas"
_HUB_FOLDER = "projects"
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")


def write_codebase_audit_to_vault(
    vault_path: str,
    audit_body: str,
    *,
    audit_date: str | None = None,
) -> dict:
    """Capture the audit body and ensure project stubs exist.

    Args:
        vault_path: Vault root.
        audit_body: Markdown body returned by the audit sub-agent. Each
            enhancement bullet should lead with a ``[[project-name]]``
            wiki-link.
        audit_date: ISO date (defaults to today). Drives the filename slug
            and the frontmatter ``date`` field.

    Returns:
        Dict with:
        - ``audit_path`` (vault-relative path of the audit file)
        - ``audit_absolute_path`` (filesystem path, paste-friendly from any repo)
        - ``linked_projects`` (sorted list of project names found in the body)
        - ``new_stubs`` (sorted list of names a hub note was created for this run)
    """
    today = audit_date or date.today().isoformat()
    title = f"codebase-enhancements-{today}"
    body = _wrap_audit_body(audit_body, today)

    audit_rel = oj_client.capture(
        title=title,
        body=body,
        folder=_AUDIT_FOLDER,
        date=today,
        type_="project-idea",
        tags=["codebase-enhancements", "audit", "daily"],
        vault_path=vault_path,
        overwrite=True,
    )

    linked = extract_project_names(body)
    new_stubs = ensure_project_stubs(vault_path, linked)

    return {
        "audit_path": audit_rel,
        "audit_absolute_path": str(Path(vault_path) / audit_rel),
        "linked_projects": sorted(linked),
        "new_stubs": sorted(new_stubs),
    }


def extract_project_names(body: str) -> set[str]:
    """Return the set of ``[[name]]`` link targets in a markdown body.

    Handles display-text links (``[[name|displayed text]]``) by keeping only
    the canonical name (the part before ``|``).
    """
    return {m.group(1).strip() for m in _WIKILINK_RE.finditer(body) if m.group(1).strip()}


def ensure_project_stubs(
    vault_path: str,
    project_names: set[str] | list[str],
) -> list[str]:
    """Create ``projects/{slug}.md`` stubs for any names without an existing hub.

    Idempotent — names whose target file already exists are skipped. Returns
    the names for which a new stub was written this call.
    """
    hub_dir = Path(vault_path) / _HUB_FOLDER
    hub_dir.mkdir(parents=True, exist_ok=True)

    new: list[str] = []
    seen_slugs: set[str] = set()

    for name in project_names:
        slug = oj_client._slugify(name)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        target = hub_dir / f"{slug}.md"
        if target.exists():
            continue

        _write_stub(vault_path, name)
        new.append(name)

    return new


def _write_stub(vault_path: str, name: str) -> None:
    """Write a minimal project-hub note via ``oj capture``."""
    body = (
        f"# {name}\n"
        "\n"
        "> Project hub — Obsidian backlinks below collect codebase audits, "
        "specs, and other vault notes that reference this project.\n"
    )
    oj_client.capture(
        title=name,
        body=body,
        folder=_HUB_FOLDER,
        type_="project-hub",
        tags=["project-hub"],
        vault_path=vault_path,
        overwrite=False,
    )


def _wrap_audit_body(body: str, today: str) -> str:
    """Prepend a standard header so the file reads well on its own.

    If the agent's body already starts with a heading we leave it alone —
    only the empty/no-heading case gets the auto-header.
    """
    stripped = body.lstrip()
    if stripped.startswith("#"):
        return body
    header = (
        f"# Codebase Enhancements — {today}\n"
        "\n"
        "Ranked by leverage for an AI-native / agentic-coding job pitch. "
        "Top of list = highest leverage. Each entry leads with a wiki-link "
        "to the project hub so Obsidian backlinks aggregate across audits.\n"
    )
    return f"{header}\n{body}"
