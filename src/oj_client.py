"""Thin subprocess wrapper for `oj` (obsidian_journal).

`oj` is the household's writer-of-record for the Obsidian vault. Every
code-daily artifact (digests, idea sheets, reddit scans) lands via
`oj capture` so frontmatter, folder routing, and filename conventions
stay in one place.

Binary resolution order:
1. ``$CODE_DAILY_OJ_BIN``
2. ``shutil.which("oj")``
3. ``~/projects/obsidian_journal/.venv/bin/oj``
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


class OjUnavailableError(RuntimeError):
    """Raised when no `oj` binary can be located."""


class OjCaptureError(RuntimeError):
    """Raised when `oj capture` fails or returns malformed output."""


def find_oj_bin() -> str:
    """Resolve the `oj` binary path or raise OjUnavailableError."""
    explicit = os.environ.get("CODE_DAILY_OJ_BIN")
    if explicit and Path(explicit).is_file() and os.access(explicit, os.X_OK):
        return explicit

    on_path = shutil.which("oj")
    if on_path:
        return on_path

    fallback = Path.home() / "projects" / "obsidian_journal" / ".venv" / "bin" / "oj"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)

    raise OjUnavailableError(
        "oj binary not found. Set $CODE_DAILY_OJ_BIN, install obsidian_journal "
        "(`pip install -e ~/projects/obsidian_journal`), or put oj on PATH."
    )


def capture(
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
    """Invoke `oj --json capture` to write a pre-rendered body into the vault.

    Args:
        title: Note title; oj slugifies this into the filename base.
        body: Pre-rendered markdown body (no frontmatter; oj writes the frontmatter).
        folder: Vault-relative folder.
        date: Frontmatter `date` (YYYY-MM-DD).
        type_: Frontmatter `type` value.
        tags: Frontmatter tags.
        extra: Additional frontmatter key=value pairs. Values must stringify cleanly.
        vault_path: Override `$OBSIDIAN_VAULT_PATH` for this call (used by tests).
        overwrite: If True and the destination file already exists, delete it first
            so we get `<slug>.md` rather than oj's `<slug>-2.md` collision suffix.
            The nightly pipeline regenerates daily files in place, so this is the
            usual mode.

    Returns:
        Vault-relative path of the written file (from oj's JSON output).
    """
    oj_bin = find_oj_bin()

    effective_vault = vault_path or os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not effective_vault:
        raise OjCaptureError("OBSIDIAN_VAULT_PATH not set and no vault_path provided")

    if overwrite:
        slug = _slugify(title)
        if slug:
            target = Path(effective_vault) / folder / f"{slug}.md"
            if target.is_file():
                target.unlink()

    argv = [oj_bin, "--json", "capture", "--title", title, "--body-file", "-"]
    if folder:
        argv.extend(["--folder", folder])
    if date:
        argv.extend(["--date", date])
    if type_:
        argv.extend(["--type", type_])
    for tag in tags or []:
        argv.extend(["--tag", tag])
    for k, v in (extra or {}).items():
        argv.extend(["--extra", f"{k}={v}"])

    env = os.environ.copy()
    env["OBSIDIAN_VAULT_PATH"] = effective_vault

    proc = subprocess.run(
        argv,
        input=body,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        raise OjCaptureError(
            f"oj capture failed (exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise OjCaptureError(f"oj capture returned non-JSON output: {proc.stdout[:200]}") from e

    path = payload.get("path")
    if not path:
        raise OjCaptureError(f"oj capture JSON missing 'path' field: {payload}")
    return path


def _slugify(value: str) -> str:
    """Mirror oj's slug rule so we can locate the destination file pre-write."""
    import re

    s = value.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
