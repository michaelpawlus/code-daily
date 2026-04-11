"""Justfile scaffolder — generates tailored justfiles for projects."""

import os
import re
import textwrap
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def detect_project(project_path: str) -> dict:
    """Read project directory and return detection results.

    Returns:
        {
            "project_name": str,
            "project_type": "python" | "node" | "unknown",
            "description": str,
            "entry_point": str | None,
            "venv_command": str,
            "test_framework": "pytest" | "unittest" | None,
            "test_dir": str | None,
            "has_venv": bool,
            "needs_databricks": bool,
            "needs_vault": bool,
            "claude_md_commands": list[str],
            "tour_content": dict,
        }
    """
    root = Path(project_path).resolve()

    result = {
        "project_name": root.name,
        "project_type": "unknown",
        "description": "",
        "entry_point": None,
        "venv_command": None,
        "test_framework": None,
        "test_dir": None,
        "has_venv": (root / ".venv").is_dir(),
        "needs_databricks": False,
        "needs_vault": False,
        "claude_md_commands": [],
        "tour_content": {
            "architecture": [],
            "key_commands": [],
            "start_here": [],
        },
    }

    pyproject = root / "pyproject.toml"
    package_json = root / "package.json"
    claude_md = root / "CLAUDE.md"
    readme_md = root / "README.md"

    # --- Detect project type and parse metadata ---
    if pyproject.is_file():
        result["project_type"] = "python"
        _parse_pyproject(pyproject, result)
    elif package_json.is_file():
        result["project_type"] = "node"
        _parse_package_json(package_json, result)

    # --- Test directory ---
    for test_name in ("tests", "test"):
        if (root / test_name).is_dir():
            result["test_dir"] = test_name
            break

    # --- Infer test framework ---
    if result["project_type"] == "python":
        if result["test_framework"] is None and result["test_dir"]:
            result["test_framework"] = "pytest"

    # --- CLAUDE.md parsing ---
    if claude_md.is_file():
        _parse_claude_md(claude_md, result)

    # --- README fallback for description ---
    if not result["description"] and readme_md.is_file():
        _parse_readme_description(readme_md, result)

    # --- Databricks / Vault detection from file contents ---
    _detect_env_references(root, pyproject, claude_md, result)

    # --- Build tour content ---
    _build_tour_content(root, result)

    return result


def generate_justfile(detection: dict) -> str:
    """Generate justfile content from detection results.

    Returns the full justfile as a string.
    """
    lines: list[str] = []
    recipes_used: list[str] = []

    project_name = detection["project_name"]
    project_type = detection["project_type"]

    # --- default ---
    lines.append("# Justfile for " + project_name)
    lines.append("")
    lines.append("default:")
    lines.append("    @just --list")
    lines.append("")
    recipes_used.append("default")

    # --- setup ---
    lines.append("# Full project setup")
    lines.append("setup:")
    if project_type == "python":
        if not detection["has_venv"]:
            lines.append("    python3 -m venv .venv")
        lines.append("    .venv/bin/pip install -e '.[dev]' 2>/dev/null || .venv/bin/pip install -e .")
    elif project_type == "node":
        lines.append("    npm install")
    if detection["needs_databricks"]:
        lines.append("    just configure-databricks")
    if detection["needs_vault"]:
        lines.append("    just configure-vault")
    lines.append("    just verify")
    lines.append("")
    recipes_used.append("setup")

    # --- verify ---
    lines.append("# Verify installation")
    lines.append("verify:")
    if detection["entry_point"]:
        venv_cmd = detection["venv_command"] or detection["entry_point"]
        lines.append(f"    {venv_cmd} --help > /dev/null && echo '✓ CLI works'")
    if detection["test_dir"]:
        if project_type == "python":
            lines.append("    .venv/bin/pytest --co -q > /dev/null && echo '✓ Tests collect'")
        elif project_type == "node":
            lines.append("    npm test -- --passWithNoTests > /dev/null && echo '✓ Tests collect'")
    if detection["needs_databricks"]:
        lines.append("    @test -n \"$DATABRICKS_HOST\" && echo '✓ DATABRICKS_HOST set' || echo '✗ DATABRICKS_HOST missing'")
    if detection["needs_vault"]:
        lines.append("    @test -n \"$OBSIDIAN_VAULT_PATH\" && echo '✓ OBSIDIAN_VAULT_PATH set' || echo '✗ OBSIDIAN_VAULT_PATH missing'")
    lines.append("")
    recipes_used.append("verify")

    # --- tour ---
    tour = detection["tour_content"]
    lines.append("# Architecture overview and getting-started pointers")
    lines.append("tour:")
    lines.append(f"    @echo '=== {project_name} ==='")
    if detection["description"]:
        lines.append(f"    @echo '{_escape_justfile(detection['description'])}'")
    lines.append("    @echo ''")
    if tour["architecture"]:
        lines.append("    @echo '── Architecture ──'")
        for entry in tour["architecture"]:
            lines.append(f"    @echo '  {_escape_justfile(entry)}'")
        lines.append("    @echo ''")
    if tour["key_commands"]:
        lines.append("    @echo '── Key Commands ──'")
        for cmd in tour["key_commands"]:
            lines.append(f"    @echo '  {_escape_justfile(cmd)}'")
        lines.append("    @echo ''")
    if tour["start_here"]:
        lines.append("    @echo '── Start Here ──'")
        for step in tour["start_here"]:
            lines.append(f"    @echo '  {_escape_justfile(step)}'")
    lines.append("")
    recipes_used.append("tour")

    # --- test ---
    if detection["test_dir"]:
        lines.append("# Run test suite")
        lines.append("test *args:")
        if project_type == "python":
            framework = detection["test_framework"] or "pytest"
            lines.append(f"    .venv/bin/{framework} {{{{args}}}}")
        elif project_type == "node":
            lines.append("    npm test -- {{args}}")
        else:
            lines.append(f"    cd {detection['test_dir']} && echo 'No test runner detected'")
        lines.append("")
        recipes_used.append("test")

    # --- run ---
    if detection["entry_point"]:
        venv_cmd = detection["venv_command"] or detection["entry_point"]
        lines.append("# Run the project CLI")
        lines.append("run *args:")
        lines.append(f"    {venv_cmd} {{{{args}}}}")
        lines.append("")
        recipes_used.append("run")

    # --- configure-databricks ---
    if detection["needs_databricks"]:
        lines.append("# Check Databricks configuration")
        lines.append("configure-databricks:")
        lines.append("    @echo 'Checking Databricks env vars...'")
        lines.append("    @test -n \"$DATABRICKS_HOST\" || (echo 'Set DATABRICKS_HOST in ~/.bashrc' && exit 1)")
        lines.append("    @test -n \"$DATABRICKS_TOKEN\" || (echo 'Set DATABRICKS_TOKEN in ~/.bashrc' && exit 1)")
        lines.append("    @echo '✓ Databricks configured'")
        lines.append("")
        recipes_used.append("configure-databricks")

    # --- configure-vault ---
    if detection["needs_vault"]:
        lines.append("# Check Obsidian vault configuration")
        lines.append("configure-vault:")
        lines.append("    @echo 'Checking Obsidian vault...'")
        lines.append("    @test -n \"$OBSIDIAN_VAULT_PATH\" || (echo 'Set OBSIDIAN_VAULT_PATH in ~/.bashrc' && exit 1)")
        lines.append("    @test -d \"$OBSIDIAN_VAULT_PATH\" || (echo 'Vault directory not found' && exit 1)")
        lines.append("    @echo '✓ Obsidian vault configured'")
        lines.append("")
        recipes_used.append("configure-vault")

    content = "\n".join(lines)
    # Ensure trailing newline
    if not content.endswith("\n"):
        content += "\n"

    return content


def scaffold_justfile(
    project_path: str, dry_run: bool = False, force: bool = False
) -> dict:
    """Main entry point: detect, generate, write.

    Returns:
        {
            "project_path": str,
            "justfile_path": str,
            "project_type": str,
            "recipes_generated": list[str],
            "written": bool,
            "dry_run": bool,
        }
    """
    root = Path(project_path).resolve()
    justfile_path = root / "justfile"

    if justfile_path.exists() and not force and not dry_run:
        raise FileExistsError(
            f"Justfile already exists at {justfile_path}. Use --force to overwrite."
        )

    detection = detect_project(project_path)
    content = generate_justfile(detection)

    # Extract recipe names from content
    recipes = _extract_recipe_names(content)

    written = False
    if not dry_run:
        justfile_path.write_text(content)
        written = True

    return {
        "project_path": str(root),
        "justfile_path": str(justfile_path),
        "project_type": detection["project_type"],
        "recipes_generated": recipes,
        "written": written,
        "dry_run": dry_run,
        "content": content if dry_run else None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _escape_justfile(text: str) -> str:
    """Escape single quotes for use inside justfile @echo statements."""
    return text.replace("'", "'\"'\"'")


def _extract_recipe_names(content: str) -> list[str]:
    """Extract recipe names from generated justfile content."""
    recipes = []
    for line in content.splitlines():
        match = re.match(r"^(\w[\w-]*)\s*(\*?\w*)?\s*:", line)
        if match and not line.startswith("#") and not line.startswith(" "):
            recipes.append(match.group(1))
    return recipes


def _parse_pyproject(path: Path, result: dict) -> None:
    """Parse pyproject.toml for project metadata."""
    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return

    project = data.get("project", {})
    result["project_name"] = project.get("name", result["project_name"])
    result["description"] = project.get("description", "")

    # Entry points
    scripts = project.get("scripts", {})
    if scripts:
        entry_name = next(iter(scripts))
        result["entry_point"] = entry_name
        result["venv_command"] = f".venv/bin/{entry_name}"

    # Test framework from dependencies or optional deps
    all_deps = []
    for dep in project.get("dependencies", []):
        all_deps.append(dep.lower())
    for group_deps in project.get("optional-dependencies", {}).values():
        for dep in group_deps:
            all_deps.append(dep.lower())

    dep_str = " ".join(all_deps)
    if "pytest" in dep_str:
        result["test_framework"] = "pytest"


def _parse_package_json(path: Path, result: dict) -> None:
    """Parse package.json for project metadata."""
    import json

    try:
        data = json.loads(path.read_text())
    except Exception:
        return

    result["project_name"] = data.get("name", result["project_name"])
    result["description"] = data.get("description", "")

    if "scripts" in data and "test" in data["scripts"]:
        result["test_framework"] = "npm"
        result["test_dir"] = result["test_dir"] or "."


def _parse_claude_md(path: Path, result: dict) -> None:
    """Parse CLAUDE.md for CLI commands and description."""
    try:
        content = path.read_text()
    except Exception:
        return

    # Extract CLI commands section
    cli_section = _extract_section(content, "CLI Commands")
    if cli_section:
        for line in cli_section.splitlines():
            line = line.strip()
            if line.startswith(result["project_name"]) or (
                result["entry_point"] and line.startswith(result["entry_point"])
            ):
                result["claude_md_commands"].append(line)
            elif re.match(r"^[\w-]+\s+[\w-]+", line) and not line.startswith("#"):
                result["claude_md_commands"].append(line)


def _parse_readme_description(path: Path, result: dict) -> None:
    """Extract description from README.md first paragraph."""
    try:
        content = path.read_text()
    except Exception:
        return

    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("!"):
            result["description"] = stripped[:200]
            break


def _extract_section(content: str, heading: str) -> str | None:
    """Extract a markdown section by heading name."""
    pattern = rf"^#+\s+{re.escape(heading)}\s*$"
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line, re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        return None

    # Find the end — next heading of same or higher level
    heading_match = re.match(r"^(#+)", lines[start - 1])
    level = len(heading_match.group(1)) if heading_match else 1
    end = len(lines)
    for i in range(start, len(lines)):
        m = re.match(r"^(#+)\s", lines[i])
        if m and len(m.group(1)) <= level:
            end = i
            break

    return "\n".join(lines[start:end])


def _detect_env_references(
    root: Path, pyproject: Path, claude_md: Path, result: dict
) -> None:
    """Detect Databricks and Vault env var references."""
    texts_to_check: list[str] = []
    for p in (pyproject, claude_md):
        if p.is_file():
            try:
                texts_to_check.append(p.read_text())
            except Exception:
                pass

    combined = " ".join(texts_to_check)
    if "DATABRICKS_HOST" in combined or "DATABRICKS_TOKEN" in combined:
        result["needs_databricks"] = True
    if "OBSIDIAN_VAULT_PATH" in combined:
        result["needs_vault"] = True


def _build_tour_content(root: Path, result: dict) -> None:
    """Build tour content from project structure."""
    tour = result["tour_content"]

    # Architecture: list top-level directories
    claude_md = root / "CLAUDE.md"
    arch_section = None
    if claude_md.is_file():
        try:
            content = claude_md.read_text()
            arch_section = (
                _extract_section(content, "Directory Structure")
                or _extract_section(content, "Project Structure")
            )
        except Exception:
            pass

    if arch_section:
        for line in arch_section.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("```"):
                tour["architecture"].append(stripped)
    else:
        # Generate from directory listing
        try:
            for entry in sorted(root.iterdir()):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    tour["architecture"].append(f"{entry.name}/")
                elif entry.name in (
                    "pyproject.toml",
                    "package.json",
                    "justfile",
                    "Makefile",
                ):
                    tour["architecture"].append(entry.name)
        except Exception:
            pass

    # Key commands
    if result["claude_md_commands"]:
        tour["key_commands"] = result["claude_md_commands"][:10]
    elif result["entry_point"]:
        tour["key_commands"].append(f"{result['entry_point']} --help")

    # Start here
    if (root / "CLAUDE.md").is_file():
        tour["start_here"].append("Read CLAUDE.md")
    if result["entry_point"]:
        cmd = result["venv_command"] or result["entry_point"]
        tour["start_here"].append(f"Run `{cmd} --help`")
    if result["test_dir"]:
        tour["start_here"].append("Run `just test`")
