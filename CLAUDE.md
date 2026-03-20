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
code-daily streak show [--json]
code-daily streak history [--json] [--days INT]
code-daily suggest [--json]
code-daily dashboard [--json]
code-daily check LEVEL [--dry-run] [--json]
code-daily news digest [--json] [--sources TEXT] [--hours INT] [--limit INT] [--no-write]
code-daily notify test
code-daily notify status
code-daily cron [--install] [--uninstall]
```

All output commands support `--json` for agent orchestration (JSON to stdout, human text to stderr).

## Agent Workflow: Themed News Digest

The `news digest` command collects raw items. Synthesis into a themed, curated digest is done by Claude Code in-session (not via API). The workflow:

1. Run `code-daily news digest --json --no-write` to collect raw items
2. Load user context from vault: `code-daily vault ideas --json`
3. Synthesize in-session: curate items into themed sections (Industry & Labs, Tools & Workflows, Research, Relevant to You, Challenge Your Thinking)
4. Write the themed digest to the vault using `write_synthesized_digest_to_vault()` from `src/news_digest`

The synthesized digest structure expected by the vault writer:
```python
{
    "overview": "2-3 sentence summary of today's themes",
    "sections": [
        {
            "name": "Section Name",
            "slug": "section-slug",
            "summary": "1-2 sentence section intro",
            "items": [
                {"title": "...", "url": "...", "source": "...", "score": 0, "commentary": "1 sentence"}
            ]
        }
    ]
}
```
