"""
Migrate code-daily cron entries to Claude Code Routines.

Claude Code Routines (launched April 2026) run on Anthropic-managed cloud
infrastructure on a schedule — minimum 1-hour interval, no local filesystem,
no desktop. This module parses a crontab block, classifies each entry, and
emits a migration plan plus a human-readable guide.

Docs: https://code.claude.com/docs/en/web-scheduled-tasks
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

ROUTINES_DOCS_URL = "https://code.claude.com/docs/en/web-scheduled-tasks"

Status = Literal["ready", "needs_refactor", "blocked"]

# Classification rules keyed by code-daily subcommand prefix (longest match wins).
# Each entry: (status, reason).
COMMAND_RULES: dict[str, tuple[Status, str]] = {
    "news digest": (
        "needs_refactor",
        "Writes the synthesized digest to your local Obsidian vault. Routines run in Anthropic's cloud with no vault access — would need to commit to a repo or mount a remote vault.",
    ),
    "news trends": ("ready", "Reads HN/Reddit/arxiv APIs only; no local filesystem state."),
    "news podcast": (
        "needs_refactor",
        "Reads the day's digest from the local vault and writes an MP3 back to the vault.",
    ),
    "check": (
        "blocked",
        "Sends desktop notifications via notify-send; cloud routines cannot reach your desktop.",
    ),
    "notify": (
        "blocked",
        "Desktop notifications cannot fire from cloud routines.",
    ),
    "vault": (
        "needs_refactor",
        "Reads from the local Obsidian vault path; not available in the cloud routine sandbox.",
    ),
    "issues list": ("ready", "Uses the GitHub API only; cloud-safe."),
    "issues top": ("ready", "Uses the GitHub API only; cloud-safe."),
    "quests discover": ("ready", "Scans your starred GitHub repos via API."),
    "quests sync-issues": ("ready", "Fetches your GitHub issues via API."),
    "streak show": ("ready", "Reads GitHub contribution graph via API."),
    "streak race": ("ready", "Reads GitHub contribution graph via API."),
}


@dataclass
class CronEntry:
    """A single parsed crontab line with its immediately-preceding comment."""

    schedule: str
    command: str
    comment: str = ""


@dataclass
class ClassifiedEntry:
    schedule: str
    command: str
    comment: str
    code_daily_command: str
    human_schedule: str
    status: Status
    reason: str
    routine_prompt: str | None = None


@dataclass
class MigrationPlan:
    entries: list[ClassifiedEntry] = field(default_factory=list)
    routines_docs_url: str = ROUTINES_DOCS_URL

    @property
    def summary(self) -> dict[str, int]:
        counts = {"ready": 0, "needs_refactor": 0, "blocked": 0}
        for e in self.entries:
            counts[e.status] = counts.get(e.status, 0) + 1
        counts["total"] = len(self.entries)
        return counts

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "entries": [asdict(e) for e in self.entries],
            "routines_docs_url": self.routines_docs_url,
        }


def parse_cron_entries(cron_text: str) -> list[CronEntry]:
    """Parse a crontab-formatted string into CronEntry records.

    Consecutive comment lines are joined with a space and attached to the next
    non-blank, non-comment line. Blank lines reset the running comment.
    """
    entries: list[CronEntry] = []
    pending_comment: list[str] = []
    for raw in cron_text.splitlines():
        line = raw.strip()
        if not line:
            pending_comment = []
            continue
        if line.startswith("#"):
            pending_comment.append(line.lstrip("#").strip())
            continue
        fields = line.split(None, 5)
        if len(fields) < 6:
            pending_comment = []
            continue
        schedule = " ".join(fields[:5])
        command = fields[5]
        entries.append(
            CronEntry(
                schedule=schedule,
                command=command,
                comment=" ".join(pending_comment),
            )
        )
        pending_comment = []
    return entries


def humanize_schedule(schedule: str) -> tuple[str, bool]:
    """Return (human_label, is_sub_hourly) for a 5-field cron expression."""
    fields = schedule.split()
    if len(fields) != 5:
        return schedule, False
    minute, hour, dom, month, dow = fields

    # Sub-hourly detection: */N minute patterns, or minute-only recurrence
    if minute.startswith("*/"):
        try:
            n = int(minute[2:])
            return f"every {n} minutes", True
        except ValueError:
            pass
    if minute == "*":
        return "every minute", True
    if "," in minute and hour == "*":
        return f"multiple times per hour ({minute})", True

    def _fmt_time(h: int, m: int) -> str:
        suffix = "AM" if h < 12 else "PM"
        display_h = h % 12 or 12
        return f"{display_h}:{m:02d} {suffix}"

    if minute.isdigit() and hour.isdigit() and month == "*":
        h, m = int(hour), int(minute)
        if dom == "*" and dow == "*":
            return f"daily at {_fmt_time(h, m)}", False
        if dom == "*" and dow in ("1-5", "MON-FRI"):
            return f"weekdays at {_fmt_time(h, m)}", False
        if dom == "*" and dow in ("0,6", "6,0", "SAT,SUN", "SUN,SAT"):
            return f"weekends at {_fmt_time(h, m)}", False

    # Hourly at :MM
    if minute.isdigit() and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"hourly at :{int(minute):02d}", False

    return f"cron: {schedule}", False


_CODE_DAILY_RE = re.compile(r"code-daily\s+([a-zA-Z][\w\- ]*?)(?=\s+--|\s*$|\s*\|)")


def extract_code_daily_command(command: str) -> str:
    """Pull the code-daily subcommand (e.g. 'news digest') out of a full shell line."""
    match = _CODE_DAILY_RE.search(command)
    if not match:
        return ""
    return match.group(1).strip()


def classify_command(code_daily_cmd: str) -> tuple[Status, str]:
    """Longest-prefix match against COMMAND_RULES. Unknown commands need refactor review."""
    if not code_daily_cmd:
        return (
            "needs_refactor",
            "Could not identify a code-daily subcommand in the cron entry.",
        )
    for key in sorted(COMMAND_RULES, key=len, reverse=True):
        if code_daily_cmd == key or code_daily_cmd.startswith(key + " "):
            return COMMAND_RULES[key]
    return (
        "needs_refactor",
        f"Unknown subcommand '{code_daily_cmd}'. Add a rule in src/routines_migrator.py:COMMAND_RULES to classify it.",
    )


def build_routine_prompt(code_daily_cmd: str, human_schedule: str) -> str:
    """Emit a ready-to-paste `/schedule` prompt for Claude Code."""
    return (
        f'/schedule {human_schedule} — "Run `code-daily {code_daily_cmd}` in the '
        f"code-daily repository. Commit any resulting changes with a short message "
        f'describing the run."'
    )


def build_plan(cron_text: str) -> MigrationPlan:
    """Parse, classify, and humanize a crontab block into a MigrationPlan."""
    plan = MigrationPlan()
    for entry in parse_cron_entries(cron_text):
        cd_cmd = extract_code_daily_command(entry.command)
        human, sub_hourly = humanize_schedule(entry.schedule)
        if sub_hourly:
            status: Status = "blocked"
            reason = "Sub-hourly schedule; Claude Code Routines require a minimum 1-hour interval."
        else:
            status, reason = classify_command(cd_cmd)
        prompt = build_routine_prompt(cd_cmd, human) if status == "ready" and cd_cmd else None
        plan.entries.append(
            ClassifiedEntry(
                schedule=entry.schedule,
                command=entry.command,
                comment=entry.comment,
                code_daily_command=cd_cmd,
                human_schedule=human,
                status=status,
                reason=reason,
                routine_prompt=prompt,
            )
        )
    return plan


_STATUS_EMOJI = {"ready": "✅", "needs_refactor": "⚠️", "blocked": "❌"}
_STATUS_LABEL = {
    "ready": "Ready to migrate",
    "needs_refactor": "Needs refactor",
    "blocked": "Blocked",
}


def render_migration_guide_md(plan: MigrationPlan, generated_at: str) -> str:
    """Render the plan as a markdown migration guide suitable for Obsidian."""
    summary = plan.summary
    lines = [
        "---",
        f"date: {generated_at}",
        "tags: [code-daily, routines, migration-guide]",
        "source: code-daily routines export",
        "---",
        "",
        "# code-daily → Claude Code Routines migration guide",
        "",
        "This guide maps your current `code-daily` cron schedule onto Claude Code",
        "Routines, which run on Anthropic-managed cloud infrastructure on a schedule.",
        "Routines are created interactively via `/schedule` inside Claude Code, or via",
        "the web UI at <https://claude.ai/code/routines>.",
        "",
        f"**Official docs:** <{plan.routines_docs_url}>",
        "",
        "## Summary",
        "",
        f"- ✅ Ready to migrate: **{summary['ready']}**",
        f"- ⚠️ Needs refactor before migration: **{summary['needs_refactor']}**",
        f"- ❌ Blocked (incompatible with cloud routines): **{summary['blocked']}**",
        f"- Total entries scanned: {summary['total']}",
        "",
        "## Entries",
        "",
        "| Status | Schedule | Command | Notes |",
        "|--------|----------|---------|-------|",
    ]
    for entry in plan.entries:
        cmd_display = f"`code-daily {entry.code_daily_command}`" if entry.code_daily_command else "_unparsed_"
        lines.append(
            f"| {_STATUS_EMOJI[entry.status]} {_STATUS_LABEL[entry.status]} "
            f"| {entry.human_schedule} | {cmd_display} | {entry.reason} |"
        )

    ready_entries = [e for e in plan.entries if e.status == "ready"]
    if ready_entries:
        lines.extend(["", "## Ready-to-paste `/schedule` prompts", ""])
        for e in ready_entries:
            lines.append(f"- {e.routine_prompt}")

    refactor_entries = [e for e in plan.entries if e.status == "needs_refactor"]
    if refactor_entries:
        lines.extend(["", "## Refactor needed before these can migrate", ""])
        for e in refactor_entries:
            lines.append(f"- `code-daily {e.code_daily_command}` — {e.reason}")

    blocked_entries = [e for e in plan.entries if e.status == "blocked"]
    if blocked_entries:
        lines.extend(["", "## Blocked (keep running locally)", ""])
        for e in blocked_entries:
            lines.append(f"- `code-daily {e.code_daily_command}` — {e.reason}")

    lines.append("")
    return "\n".join(lines)
