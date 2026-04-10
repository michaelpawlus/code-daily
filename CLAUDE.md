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

**Important:** Always invoke as `.venv/bin/code-daily`, never as `python -m code_daily` (there is no `__main__.py` module entry point).

```
code-daily issues list [--json] [--labels TEXT] [--repo TEXT] [--limit INT]
code-daily issues top [--json]
code-daily vault scan [--json] [--since INT] [--folders TEXT] [--search TEXT]
code-daily vault ideas [--json]
code-daily streak show [--json]
code-daily streak history [--json] [--days INT]
code-daily suggest [--json]
code-daily diversity [--json] [--days INT]
code-daily ideas from-news [--json] [--hours INT] [--limit INT]
code-daily ideas from-reddit [--json] [--subreddit TEXT] [--count INT] [--limit INT]
code-daily ideas list [--json] [--status TEXT]
code-daily ideas add CONTENT [--json]
code-daily ideas promote IDEA_ID [--json]
code-daily ideas sync [--json]
code-daily quests list [--json] [--status TEXT] [--limit INT]
code-daily quests add TITLE [--json] [--description TEXT]
code-daily quests accept QUEST_ID [--json]
code-daily quests complete QUEST_ID [--json]
code-daily quests skip QUEST_ID [--json] [--save-idea]
code-daily quests summary [--json]
code-daily quests sync-issues [--json]
code-daily quests scan-todos [--json]
code-daily quests scan-skillvault [--json]
code-daily quests discover [--json]
code-daily quests enhance QUEST_ID [--json]
code-daily quests enhance-batch [--json] [--limit INT]
code-daily quests ai-status [--json]
code-daily achievements list [--json] [--category TEXT]
code-daily dashboard [--json]
code-daily check LEVEL [--dry-run] [--json]
code-daily news digest [--json] [--sources TEXT] [--hours INT] [--limit INT] [--no-write]
code-daily news trends [--json] [--days INT]
code-daily news podcast [--json] [--date TEXT] [--voice TEXT]
code-daily notify test
code-daily notify status
code-daily cron [--install] [--uninstall]
```

All output commands support `--json` for agent orchestration (JSON to stdout, human text to stderr).

## Quest Discovery Sources

Quests can be created from several sources, each with its own sync command:

- `quests sync-issues` — your own GitHub issues
- `quests scan-todos` — TODO/FIXME comments in this repo's Python files
- `quests scan-skillvault` — incomplete-work markers (TODO, "ready to build", "planned", "coming soon", etc.) surfaced from `skillvault`'s cross-project index of CLAUDE.md files, skill SKILL.md files, and specs. Requires `skillvault` on PATH (or installed at `~/projects/skillvault/.venv/bin/skillvault`); silently no-ops if absent. Run `skillvault scan` first to populate the index.
- `quests discover` — external good-first-issue candidates from starred GitHub repos

All four are deduped via `(source, source_ref)` so they're safe to re-run.

## Agent Workflow: Themed News Digest

The `news digest` command collects raw items. Synthesis into a themed, curated digest is done by Claude Code in-session (not via API). The workflow:

1. Run `code-daily news digest --json --no-write` to collect raw items
2. Load user context from vault: `code-daily vault ideas --json`
3. Synthesize in-session: curate items into themed sections (Industry & Labs, Tools & Workflows, Research, Relevant to You, Challenge Your Thinking)
4. Write the themed digest to the vault using `write_synthesized_digest_to_vault()` from `src/news_digest`
5. Generate TTS podcast: `code-daily news podcast --json` (reads today's synthesized digest, outputs MP3)

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

## Agent Workflow: TTS Podcast Generation

After synthesizing the themed news digest, generate a podcast audio file:

1. Run `code-daily news podcast --json` (reads today's synthesized digest from vault)
2. Or specify a date: `code-daily news podcast --json --date 2026-03-28`
3. Returns metadata including the vault file path and generated script

The command reads the synthesized digest from `ai-news/{date}.md`, converts it to a
natural speech script, and generates an MP3 at `ai-news/podcasts/{date}.mp3` using
edge-tts (Microsoft TTS, no API key required).

Available voices: `edge-tts --list-voices`
Default voice: `en-US-AndrewMultilingualNeural`

## Agent Workflow: News-Informed Project Ideas

Generate project ideas tied to trending topics. The workflow:

1. Run `code-daily ideas from-news --json` to collect seed data (trending topics + user interests + recent domains)
2. Claude Code synthesizes 3 project ideas in-session, each with: title, description, why_now, skills_demonstrated, complexity
3. Write to vault using `write_project_ideas_to_vault()` from `src/idea_generator`

The synthesized ideas structure expected by the vault writer:
```python
{
    "ideas": [
        {
            "title": "Project Name",
            "description": "What to build",
            "why_now": "Tied to trending topic X",
            "skills_demonstrated": ["skill1", "skill2"],
            "trending_source": "HN/Reddit item that inspired it",
            "complexity": "weekend"  # or "week", "multi-week"
        }
    ],
    "generated_from": "2026-03-25"
}
```

## Agent Workflow: Reddit Community Problem Scanner

Find real pain points in active communities and suggest projects. The workflow:

1. Run `code-daily ideas from-reddit --json` to scan random community subreddits for problem posts
2. Claude Code identifies recurring pain points and synthesizes a project idea
3. Write to vault using `write_reddit_scan_to_vault()` from `src/reddit_scanner`

The synthesized scan structure expected by the vault writer:
```python
{
    "subreddit": "homelab",
    "problem_summary": "What users are struggling with",
    "evidence_posts": [
        {"title": "...", "url": "...", "comment_count": 32}
    ],
    "project_idea": {
        "title": "Project Name",
        "description": "What to build",
        "why_build_it": "Why this solves a real problem",
        "target_users": "Who benefits",
        "skills_demonstrated": ["skill1", "skill2"]
    }
}
```

## Suggest Command: Freshness Tracking

The `suggest` command tracks previously suggested ideas in a `suggestion_log` table. Scoring adjustments:
- **Staleness penalty:** -3 points per time an idea was suggested in the last 14 days
- **Domain diversity bonus:** +3 points if the idea's domain hasn't been suggested in the last 30 days

This prevents the same ideas from dominating the suggestions list day after day.
