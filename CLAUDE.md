# Claude Code Notes

## Running Tests

This project uses a virtual environment. To run pytest, use the venv python:

```bash
.venv/bin/pytest
```

Or for verbose output:

```bash
.venv/bin/pytest -v
```

Do not use system python as pytest is not installed globally.

## CLI Commands

The project exposes a `code-daily` CLI (Typer-based). Install with `pip install -e .` in the venv.

```
code-daily issues list [--json] [--labels TEXT] [--repo TEXT] [--limit INT]
code-daily issues top [--json]
code-daily vault scan [--json] [--since INT] [--folders TEXT] [--search TEXT]
code-daily vault ideas [--json]
code-daily suggest [--json]
code-daily dashboard [--json]
code-daily check LEVEL [--dry-run] [--json]
code-daily news digest [--json] [--sources TEXT] [--hours INT] [--limit INT] [--no-write]
code-daily notify test
code-daily notify status
code-daily cron
```

All output commands support `--json` for agent orchestration (JSON to stdout, human text to stderr).
