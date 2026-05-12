"""Shared pytest fixtures for code-daily."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _slugify(value: str) -> str:
    """Mirror oj's slug rule so the stub matches real filenames."""
    s = value.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _dump_frontmatter(fm: dict) -> str:
    """Render frontmatter the way ``oj capture`` (python-frontmatter) does.

    Keys are sorted alphabetically. Lists render block-style. All scalar values
    quoted as strings (matches the actual output observed from ``oj``).
    """
    lines = ["---"]
    for key in sorted(fm.keys()):
        value = fm[key]
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"- {item}")
        else:
            lines.append(f"{key}: '{value}'")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _fake_oj_capture(
    title: str,
    body: str,
    folder: str,
    *,
    date: str | None = None,
    type_: str | None = None,
    tags: list[str] | None = None,
    extra: dict[str, str] | None = None,
    vault_path: str | None = None,
    overwrite: bool = False,
) -> str:
    """Stub of oj_client.capture that writes to the filesystem directly.

    Mirrors oj's on-disk behavior closely enough for round-trip tests:
    slug-based filename, frontmatter shape, ``-2.md`` collision suffix when
    ``overwrite=False``.
    """
    if vault_path is None:
        raise RuntimeError("fake oj_capture stub requires vault_path in tests")

    fm: dict = {}
    if date:
        fm["date"] = date
    if type_:
        fm["type"] = type_
    if tags:
        fm["tags"] = list(tags)
    if extra:
        for k, v in extra.items():
            fm[k] = v

    slug = _slugify(title) or "untitled"
    folder_path = Path(vault_path) / folder if folder else Path(vault_path)
    folder_path.mkdir(parents=True, exist_ok=True)

    candidate = folder_path / f"{slug}.md"
    if overwrite and candidate.exists():
        candidate.unlink()

    n = 2
    while candidate.exists():
        candidate = folder_path / f"{slug}-{n}.md"
        n += 1

    if fm:
        content = _dump_frontmatter(fm) + "\n" + body
    else:
        content = body
    candidate.write_text(content, encoding="utf-8")

    return str(candidate.relative_to(vault_path))


@pytest.fixture(autouse=True)
def _stub_oj_capture(monkeypatch):
    """Swap ``oj_client.capture`` for a filesystem stub across all tests.

    The real wrapper shells out to the ``oj`` binary; tests should never
    require that binary on PATH. Tests that explicitly want to exercise the
    subprocess path can opt out by re-patching with their own implementation.
    """
    monkeypatch.setattr("src.oj_client.capture", _fake_oj_capture)
    # Also patch the re-exports inside writer modules that imported the
    # symbol at module-import time (`from src import oj_client` re-uses the
    # module-level binding, so the monkeypatch above is sufficient — but if
    # any test imports `from src.oj_client import capture` we'd need to patch
    # there too. Current writer code uses `oj_client.capture`, so we're fine.)
