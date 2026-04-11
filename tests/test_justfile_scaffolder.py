"""Tests for the justfile scaffolder."""

import json
import tempfile
from pathlib import Path

import pytest

from src.justfile_scaffolder import detect_project, generate_justfile, scaffold_justfile


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestDetectPythonProject:
    """test_detect_python_project — mock a pyproject.toml, verify detection."""

    def test_basic_python_detection(self, temp_dir):
        """Detects Python project from pyproject.toml."""
        (temp_dir / "pyproject.toml").write_text(
            '[project]\nname = "my-tool"\ndescription = "A cool tool"\n'
            '\n[project.scripts]\nmy-tool = "src.cli:main"\n'
        )
        (temp_dir / "tests").mkdir()

        result = detect_project(str(temp_dir))

        assert result["project_type"] == "python"
        assert result["project_name"] == "my-tool"
        assert result["description"] == "A cool tool"
        assert result["entry_point"] == "my-tool"
        assert result["venv_command"] == ".venv/bin/my-tool"
        assert result["test_dir"] == "tests"
        assert result["test_framework"] == "pytest"

    def test_python_no_scripts(self, temp_dir):
        """Python project without entry points."""
        (temp_dir / "pyproject.toml").write_text(
            '[project]\nname = "lib-only"\n'
        )

        result = detect_project(str(temp_dir))

        assert result["project_type"] == "python"
        assert result["entry_point"] is None

    def test_has_venv_detection(self, temp_dir):
        """Detects existing .venv directory."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "x"\n')
        (temp_dir / ".venv").mkdir()

        result = detect_project(str(temp_dir))

        assert result["has_venv"] is True


class TestDetectNodeProject:
    """test_detect_node_project — mock a package.json, verify detection."""

    def test_basic_node_detection(self, temp_dir):
        """Detects Node project from package.json."""
        (temp_dir / "package.json").write_text(json.dumps({
            "name": "my-app",
            "description": "A node app",
            "scripts": {"test": "jest"},
        }))

        result = detect_project(str(temp_dir))

        assert result["project_type"] == "node"
        assert result["project_name"] == "my-app"
        assert result["description"] == "A node app"
        assert result["test_framework"] == "npm"


class TestDetectDatabricksProject:
    """test_detect_databricks_project — project with Databricks env var refs."""

    def test_databricks_from_claude_md(self, temp_dir):
        """Detects Databricks need from CLAUDE.md env var references."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "dbx-tool"\n')
        (temp_dir / "CLAUDE.md").write_text(
            "# My Project\n\nRequires DATABRICKS_HOST and DATABRICKS_TOKEN.\n"
        )

        result = detect_project(str(temp_dir))

        assert result["needs_databricks"] is True

    def test_vault_from_claude_md(self, temp_dir):
        """Detects Vault need from CLAUDE.md env var references."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "vault-tool"\n')
        (temp_dir / "CLAUDE.md").write_text(
            "# My Project\n\nWrites to OBSIDIAN_VAULT_PATH.\n"
        )

        result = detect_project(str(temp_dir))

        assert result["needs_vault"] is True


class TestGenerateJustfile:
    """test_generate_justfile_has_core_recipes — output contains setup/verify/tour/test."""

    def test_core_recipes_present(self, temp_dir):
        """Generated justfile has default, setup, verify, tour."""
        (temp_dir / "pyproject.toml").write_text(
            '[project]\nname = "my-proj"\ndescription = "Test"\n'
        )
        (temp_dir / "tests").mkdir()

        detection = detect_project(str(temp_dir))
        content = generate_justfile(detection)

        assert "default:" in content
        assert "setup:" in content
        assert "verify:" in content
        assert "tour:" in content
        assert "test *args:" in content

    def test_entry_point_run_recipe(self, temp_dir):
        """test_generate_justfile_with_entry_point — run recipe uses detected entry point."""
        (temp_dir / "pyproject.toml").write_text(
            '[project]\nname = "coolcli"\n\n[project.scripts]\ncoolcli = "src.main:app"\n'
        )

        detection = detect_project(str(temp_dir))
        content = generate_justfile(detection)

        assert "run *args:" in content
        assert ".venv/bin/coolcli" in content

    def test_databricks_recipe_added(self, temp_dir):
        """Adds configure-databricks when needed."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "dbx"\n')
        (temp_dir / "CLAUDE.md").write_text("Uses DATABRICKS_HOST.\n")

        detection = detect_project(str(temp_dir))
        content = generate_justfile(detection)

        assert "configure-databricks:" in content
        assert "DATABRICKS_HOST" in content

    def test_vault_recipe_added(self, temp_dir):
        """Adds configure-vault when needed."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "vlt"\n')
        (temp_dir / "CLAUDE.md").write_text("Uses OBSIDIAN_VAULT_PATH.\n")

        detection = detect_project(str(temp_dir))
        content = generate_justfile(detection)

        assert "configure-vault:" in content
        assert "OBSIDIAN_VAULT_PATH" in content

    def test_no_test_recipe_without_test_dir(self, temp_dir):
        """No test recipe when no test directory."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "no-tests"\n')

        detection = detect_project(str(temp_dir))
        content = generate_justfile(detection)

        assert "test *args:" not in content


class TestScaffoldDryRun:
    """test_scaffold_dry_run — does not write file."""

    def test_dry_run_no_write(self, temp_dir):
        """Dry run returns content but does not create file."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "dr"\n')

        result = scaffold_justfile(str(temp_dir), dry_run=True)

        assert result["written"] is False
        assert result["dry_run"] is True
        assert result["content"] is not None
        assert not (temp_dir / "justfile").exists()


class TestScaffoldForce:
    """test_scaffold_force_overwrites — overwrites existing justfile."""

    def test_force_overwrites(self, temp_dir):
        """Force flag overwrites an existing justfile."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "fw"\n')
        (temp_dir / "justfile").write_text("old content")

        result = scaffold_justfile(str(temp_dir), force=True)

        assert result["written"] is True
        content = (temp_dir / "justfile").read_text()
        assert "old content" not in content
        assert "default:" in content


class TestScaffoldNoForceErrors:
    """test_scaffold_no_force_errors — errors when justfile exists."""

    def test_errors_without_force(self, temp_dir):
        """Raises FileExistsError when justfile exists and no --force."""
        (temp_dir / "pyproject.toml").write_text('[project]\nname = "nf"\n')
        (temp_dir / "justfile").write_text("existing")

        with pytest.raises(FileExistsError, match="already exists"):
            scaffold_justfile(str(temp_dir))
