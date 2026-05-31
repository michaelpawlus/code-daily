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
code-daily streak race [--json]
code-daily streak history [--json] [--days INT]
code-daily streak insights [--json] [--days INT]
code-daily suggest [--json]
code-daily diversity [--json] [--days INT]
code-daily ideas from-news [--json] [--hours INT] [--limit INT]
code-daily ideas from-reddit [--json] [--subreddit TEXT] [--count INT] [--limit INT]
code-daily ideas list [--json] [--status TEXT]
code-daily ideas add CONTENT [--json]
code-daily ideas promote IDEA_ID [--json]
code-daily ideas sync [--json]
code-daily circleback add CONTENT [--kind TEXT] [--priority TEXT] [--date TEXT] [--note TEXT] [--json]
code-daily circleback list [--json] [--status TEXT] [--kind TEXT]
code-daily circleback due [--json]
code-daily circleback done ITEM_ID [--json]
code-daily circleback drop ITEM_ID [--json]
code-daily circleback snooze ITEM_ID DATE [--json]
code-daily circleback promote-to-issue ITEM_ID [--repo TEXT] [--json]
code-daily circleback context [--json]
code-daily quests list [--json] [--status TEXT] [--limit INT]
code-daily quests add TITLE [--json] [--description TEXT]
code-daily quests accept QUEST_ID [--json]
code-daily quests complete QUEST_ID [--json]
code-daily quests skip QUEST_ID [--json] [--save-idea]
code-daily quests summary [--json]
code-daily quests sync-issues [--json]
code-daily quests scan-todos [--json]
code-daily quests scan-skillvault [--json]
code-daily quests scan-launchpad [--json] [--max-grade TEXT]
code-daily quests discover [--json]
code-daily quests discover-all [--json]
code-daily quests enhance QUEST_ID [--json]
code-daily quests enhance-batch [--json] [--limit INT]
code-daily quests ai-status [--json]
code-daily achievements list [--json] [--category TEXT]
code-daily dashboard [--json] [--since INT]
code-daily check LEVEL [--dry-run] [--json]
code-daily news digest [--json] [--sources TEXT] [--hours INT] [--limit INT] [--no-write]
code-daily news trends [--json] [--days INT]
code-daily news podcast [--json] [--date TEXT] [--voice TEXT]
code-daily notify test
code-daily notify status
code-daily scaffold justfile [PROJECT_PATH] [--json] [--dry-run] [--force]
code-daily cron [--install] [--uninstall]
code-daily routines plan [--json]
code-daily routines export [--json] [--output PATH]
code-daily portfolio sweep [--root PATH] [--json] [--dry-run]
code-daily portfolio history [--project NAME] [--days INT] [--json]
code-daily launchpad sweep [--root PATH] [--json] [--dry-run]
code-daily launchpad history [--project NAME] [--days INT] [--json]
code-daily launchpad show NAME [--json]
```

All output commands support `--json` for agent orchestration (JSON to stdout, human text to stderr).

## Obsidian as the Universal Output Target

Vault writes go through **`oj`** (`obsidian_journal`) — see `~/projects/obsidian_journal/CLAUDE.md`. Use `oj --json journal -t reading -q "..."` for capture and `oj --json plan -q "..."` for time-blocked planning so frontmatter, folder routing, and filename conventions stay in one place. Don't write directly under `$OBSIDIAN_VAULT_PATH`.

## Claude Code Routines Migration

`code-daily routines plan` / `code-daily routines export` classify your current
`code-daily cron` entries by how migratable they are to native Claude Code
Routines (cloud-hosted scheduled tasks, launched April 2026). Statuses:

- **✅ ready** — cloud-safe, emits a ready-to-paste `/schedule` prompt
- **⚠️ needs_refactor** — relies on local vault or filesystem state
- **❌ blocked** — fundamentally incompatible (desktop notifications, sub-hourly)

Classification rules live in `src/routines_migrator.py:COMMAND_RULES`. Add a
rule there whenever a new recurring command is introduced so the migration
report stays accurate. Routines docs: <https://code.claude.com/docs/en/web-scheduled-tasks>.

## Portfolio Sweep

`code-daily portfolio sweep` shells out to `agent-ready score --root ~/projects`
and (best-effort) `portfolio-audit list`, merges the two per project path, and
persists one row per project into the `portfolio_snapshots` table. Each run
diffs against the previous snapshot per project so the JSON output contains a
`changes` array — that's the "moved 5 repos from C to A in 30 days" feed.

Binary resolution order:

1. `$CODE_DAILY_AGENT_READY_BIN` / `$CODE_DAILY_PORTFOLIO_AUDIT_BIN`
2. `shutil.which(...)` on PATH
3. Per-project venvs at `~/projects/{agent-ready,portfolio-audit}/.venv/bin/...`

`agent-ready` missing is a hard error. `portfolio-audit` missing degrades to
a warning — activity fields (`days_since_last_commit`, `commits_30d`,
`has_cli`) become null but scoring continues. `--dry-run` skips persistence.

Read back with `code-daily portfolio history [--project NAME] [--days INT]`.

## Launchpad

`code-daily launchpad sweep` scores every shippable Python tool under
`~/projects` against a local-only readiness checklist (no network) and
persists a snapshot to `launchpad_snapshots`. A "shippable" is any project
with a `pyproject.toml` declaring at least one `[project.scripts]` entry —
that filter is what separates a publishable CLI from a research notebook.

Signals (weights total 100):

- `has_readme` (10), `readme_substantial` ≥800 bytes (5),
  `readme_has_install` (5), `readme_has_usage` (10)
- `has_license` (10), `has_changelog` (10)
- `has_tests` (15), `has_ci` GitHub Actions (15)
- `has_recent_commit` ≤30 days (10), `has_cli_entry` (10)

Grades: A ≥85, B ≥70, C ≥55, D ≥40, else F. Same diff/grade-distribution
shape as `portfolio sweep` so the JSON outputs compose. Read back per-project
detail with `launchpad show NAME` (full passing/missing signal breakdown)
and longitudinal grade movement with `launchpad history`.

Launchpad answers a different question than `portfolio sweep` — portfolio
asks "is this project well-built?", launchpad asks "is this project
shareable yet?". A project can be a high-quality A in portfolio terms
(strong code, tests, agent-ready CLI) while still being a launchpad D
because nobody outside this repo can find it. Logic lives in
`src/launchpad.py`.

`code-daily dashboard` also surfaces a "Portfolio Activation Health" panel
underneath the streak — current grade distribution, movement counts vs the
baseline snapshot, top movers up/down, and a stale-projects list (any project
whose latest snapshot reports `days_since_last_commit >= 30`). The panel's
lookback window is controlled by `--since DAYS` (default 30); the baseline is
the most recent snapshot per project strictly older than that cutoff. JSON
output exposes the same data under the top-level `portfolio_activation` key.
Logic lives in `src/portfolio_activation.py`.

## Quest Discovery Sources

Quests can be created from several sources, each with its own sync command:

- `quests sync-issues` — your own GitHub issues
- `quests scan-todos` — TODO/FIXME comments in this repo's Python files
- `quests scan-skillvault` — incomplete-work markers (TODO, "ready to build", "planned", "coming soon", etc.) surfaced from `skillvault`'s cross-project index of CLAUDE.md files, skill SKILL.md files, and specs. Requires `skillvault` on PATH (or installed at `~/projects/skillvault/.venv/bin/skillvault`); silently no-ops if absent. Run `skillvault scan` first to populate the index.
- `quests scan-launchpad` — turn low-grade `launchpad sweep` projects into polish quests. One quest per project (not per missing signal — that would flood the queue); the description enumerates the missing readiness signals (`has_license`, `has_ci`, etc.). Threshold defaults to D and below (`--max-grade D`). Dedup key is the project path (`source_ref=launchpad:{path}`), so renames of the human-facing name don't cause duplicates. Calls `launchpad.run_sweep(persist=False)` — `launchpad sweep` remains the single writer of snapshot rows. Closes the activation loop: launchpad scores → low-grade quests → user polishes → next sweep grades the project up.
- `quests discover` — external good-first-issue candidates from starred GitHub repos

All five are deduped via `(source, source_ref)` so they're safe to re-run.

`quests discover-all` runs every source above (plus `sync-beacon-gaps`) in one
shot, local-only first (scan-todos, scan-skillvault, scan-launchpad) then
network-bound (sync-beacon-gaps, sync-issues, discover). Per-source failures are contained:
a missing binary or a bad GitHub token shows up as `[skip]` or `[err]` in the
per-source line while the rest of the batch keeps going. Returns aggregated
totals plus a `sources` array. Helper logic lives in `src/quest_discovery.py`
and is shared by the five single-source commands.

**beacon integration — `gaps export` not `gaps list`.** `sync-beacon-gaps`
calls `beacon gaps export --json`, which emits quest-shaped dicts
(`title`, `source`, `source_ref`, `description`) ready for the quest queue.
Do **not** swap in `beacon gaps list --json` — that returns the v1 envelope
`{"schema_version": 1, "gaps": [...]}` of raw gap rows, intended for analytical
consumers like `stack-quest arcs suggest`. See beacon's CLAUDE.md "Gaps
subcommand contract" for the full list/export distinction.

## Agent Workflow: Codebase Audit + Project Hubs

The nightly `/newsandideas` pipeline delegates a codebase enhancement audit to
a sub-agent. The agent must return a markdown list where **every bullet leads
with an Obsidian wiki-link** to the project name (e.g. `- [[conductor]] add
...`). The orchestrator then writes the result via:

```python
from src.codebase_audit import write_codebase_audit_to_vault
result = write_codebase_audit_to_vault(vault_path, audit_body)
```

This does two things:

1. Captures the body to `Project Ideas/codebase-enhancements-{date}.md` (same-day
   re-runs overwrite — no `-2.md` collisions).
2. For every `[[name]]` link target, creates a one-line stub at
   `projects/{slug}.md` if one doesn't exist yet. The stub exists only to
   resolve the link cleanly so Obsidian's backlinks panel can aggregate every
   audit/spec/idea that mentions a given project. Stubs are tagged
   `project-hub`.

Returns a dict with `audit_path`, `audit_absolute_path` (paste-friendly),
`linked_projects` (everything backlinked this run), and `new_stubs` (hubs
created this run — surface these to the user so they know what's new).
Logic lives in `src/codebase_audit.py`.

## Circle-Back: Earmarking Items to Revisit

`code-daily circleback` is a lightweight backlog for things you want to come
back to but can't act on right now — work you started and mean to continue,
new project ideas worth retaining, or anything surfaced during a
`/newsandideas` run that deserves more than a fleeting mention. It is
deliberately distinct from its two neighbours:

- **`quests`** is the prioritized *work queue* fed by automated discovery sources.
- **`ideas`** is the IDEAS.md-backed running list of coding ideas.

Circle-back adds two things neither has: an optional **snooze-until date**
(`circle_back_date`) so an item stays quiet until it's due, and an explicit
**priority** (`high`/`medium`/`low`) that signals to the agent what *you* think
is important. Each item has a **kind** (`continue`, `project`, or `idea`) and a
lifecycle of `open → done | dropped | promoted`.

Items live in the `circleback_items` table; logic is in `src/circleback.py`
(`CircleBackManager`). `circleback add` dedupes on `(source, source_ref)` so
automated capture is safe to re-run. `circleback due` shows only items that are
actionable now (undated, or past their snooze date); the rest stay hidden until
they come due. `circleback promote-to-issue` creates a real GitHub issue via
`gh issue create` (see `gh_issues.create_issue`), records the URL, and marks the
item `promoted` — the bridge for when an earmark is finally ready to act on.

### newsandideas integration

The nightly `/newsandideas` pipeline should bracket its run with circle-back:

1. **Start of run — load priorities.** Run `code-daily circleback context --json`
   and feed the result to the agent as "what the user has already flagged as
   important." The payload groups due items by kind, counts high-priority items,
   and reports how many are still snoozed, so new suggestions can defer to or
   build on the existing backlog instead of duplicating it.
2. **End of run — capture overflow.** When a session surfaces more good work
   than fits in one day, earmark the rest rather than dropping it:
   `code-daily circleback add "<thing>" --kind <continue|project|idea> --priority high [--date YYYY-MM-DD]`.
   Use `--source newsandideas` style refs only via the Python API
   (`CircleBackManager.add(..., source="newsandideas", source_ref=...)`) when you
   need dedup across runs.

This closes the loop: each run reads back the priorities the user set, and the
overflow from a run becomes the seed for the next one.

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
