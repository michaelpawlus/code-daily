---
date: 2026-04-10
status: Ready to build
complexity: evening
tags: [spec, cli-tooling, developer-experience, justfiles]
---

# Justfile Scaffolder

Add a `code-daily scaffold justfile [PROJECT_PATH]` command that generates a
tailored justfile for any project by reading its structure.

## Motivation

We just built a justfile for advancement-codex by hand. The pattern
(setup/tour/verify/test/configure-*) is portable across all 30+ projects.
This command codifies the pattern so justfiles can be stamped out quickly.

## CLI Interface

```
code-daily scaffold justfile [PROJECT_PATH] [--json] [--dry-run] [--force]
```

- `PROJECT_PATH`: Directory to scaffold (default: current directory)
- `--dry-run`: Print the generated justfile to stdout instead of writing
- `--force`: Overwrite an existing justfile
- `--json`: Output metadata as JSON (file path, recipes generated, project type detected)

## Detection Logic

The scaffolder reads the target project directory and detects:

| Signal | File checked | What it tells us |
|--------|-------------|-----------------|
| Python project | `pyproject.toml` | Package name, entry points, test framework, optional deps |
| CLAUDE.md | `CLAUDE.md` | CLI commands, agent persona, project description |
| README.md | `README.md` | Project description (fallback) |
| Existing venv | `.venv/` | Skip venv creation in setup |
| Test directory | `tests/`, `test/` | Test recipe framework |
| Databricks deps | `pyproject.toml` deps, env var refs | Add configure-databricks recipe |
| Node project | `package.json` | npm-based setup instead of pip |

## Generated Recipes

Every justfile gets these core recipes:

| Recipe | What it does |
|--------|-------------|
| `default` | `just --list` |
| `setup` | Chain: check runtime, create env, install deps, optional config, verify |
| `verify` | Check CLI works, tests pass, required env vars set |
| `tour` | Architecture overview, key commands, "start here" pointers |
| `test` | Run test suite with pass-through args |
| `run` | Shortcut for the project's CLI entry point (if detected) |

Conditional recipes added based on detection:

| Condition | Recipe added |
|-----------|-------------|
| Databricks env vars referenced | `configure-databricks` |
| `OBSIDIAN_VAULT_PATH` referenced | `configure-vault` |
| Entry point in pyproject.toml | `run *args` mapped to that entry point |

## Source Module

**New file**: `src/justfile_scaffolder.py`

```python
def detect_project(project_path: str) -> dict:
    """Read project directory and return detection results.

    Returns:
        {
            "project_name": str,
            "project_type": "python" | "node" | "unknown",
            "description": str,
            "entry_point": str | None,      # e.g. "advcodex"
            "venv_command": str,             # e.g. ".venv/bin/advcodex"
            "test_framework": "pytest" | "unittest" | None,
            "test_dir": str | None,
            "has_venv": bool,
            "needs_databricks": bool,
            "needs_vault": bool,
            "claude_md_commands": list[str], # CLI commands from CLAUDE.md
            "tour_content": dict,            # architecture + key commands
        }
    """

def generate_justfile(detection: dict) -> str:
    """Generate justfile content from detection results.

    Returns the full justfile as a string.
    """

def scaffold_justfile(project_path: str, dry_run: bool = False, force: bool = False) -> dict:
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
```

## CLI Registration

In `typer_cli.py`:

```python
scaffold_app = typer.Typer(help="Scaffolding commands")
app.add_typer(scaffold_app, name="scaffold")

@scaffold_app.command("justfile")
def scaffold_justfile_cmd(
    project_path: str = typer.Argument(".", help="Project directory to scaffold"),
    json_output: bool = typer.Option(False, "--json"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force: bool = typer.Option(False, "--force"),
):
```

## Tour Content Generation

The `tour` recipe content is built from:

1. **Architecture section**: List top-level directories with one-line descriptions.
   Read from CLAUDE.md "Directory Structure" or "Project Structure" section if present,
   otherwise generate from directory listing.

2. **Key commands section**: Extract CLI commands from CLAUDE.md "CLI Commands" section
   or from `[project.scripts]` in pyproject.toml.

3. **Start here section**: Always includes:
   - "Read CLAUDE.md" (if exists)
   - "Run `<entry_point> --help`" (if entry point detected)
   - "Run `just test`"

## Edge Cases

- **No pyproject.toml or package.json**: Generate a minimal justfile with just
  `tour` and `test` (if test dir found)
- **Justfile already exists**: Error unless `--force`
- **Project is code-daily itself**: Works fine — generates a justfile for code-daily

## Tests

Test in `tests/test_justfile_scaffolder.py`:

- `test_detect_python_project` — mock a pyproject.toml, verify detection
- `test_detect_node_project` — mock a package.json, verify detection
- `test_detect_databricks_project` — project with Databricks env var refs
- `test_generate_justfile_has_core_recipes` — output contains setup/verify/tour/test
- `test_generate_justfile_with_entry_point` — `run` recipe uses detected entry point
- `test_scaffold_dry_run` — does not write file
- `test_scaffold_force_overwrites` — overwrites existing justfile
- `test_scaffold_no_force_errors` — errors when justfile exists
