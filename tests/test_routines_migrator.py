"""Tests for src.routines_migrator."""

from src.routines_migrator import (
    ROUTINES_DOCS_URL,
    build_plan,
    build_routine_prompt,
    classify_command,
    extract_code_daily_command,
    humanize_schedule,
    parse_cron_entries,
    render_migration_guide_md,
)


class TestParseCronEntries:
    def test_parses_schedule_and_command(self):
        entries = parse_cron_entries("0 8 * * * cd /repo && code-daily news digest")
        assert len(entries) == 1
        assert entries[0].schedule == "0 8 * * *"
        assert "code-daily news digest" in entries[0].command

    def test_attaches_preceding_comment(self):
        text = (
            "# daily news digest\n"
            "0 8 * * * code-daily news digest\n"
        )
        entries = parse_cron_entries(text)
        assert entries[0].comment == "daily news digest"

    def test_blank_line_resets_comment(self):
        text = (
            "# stale comment\n"
            "\n"
            "0 8 * * * code-daily news digest\n"
        )
        entries = parse_cron_entries(text)
        assert entries[0].comment == ""

    def test_multiple_entries(self):
        text = (
            "0 8 * * * code-daily news digest\n"
            "0 10 * * * code-daily check 1\n"
            "0 16 * * * code-daily check 2\n"
        )
        assert len(parse_cron_entries(text)) == 3

    def test_ignores_malformed_lines(self):
        assert parse_cron_entries("not a cron line") == []

    def test_empty_input(self):
        assert parse_cron_entries("") == []


class TestHumanizeSchedule:
    def test_daily_morning(self):
        label, sub_hourly = humanize_schedule("0 8 * * *")
        assert label == "daily at 8:00 AM"
        assert sub_hourly is False

    def test_daily_afternoon(self):
        label, _ = humanize_schedule("30 16 * * *")
        assert label == "daily at 4:30 PM"

    def test_noon(self):
        label, _ = humanize_schedule("0 12 * * *")
        assert label == "daily at 12:00 PM"

    def test_midnight(self):
        label, _ = humanize_schedule("0 0 * * *")
        assert label == "daily at 12:00 AM"

    def test_weekdays(self):
        label, _ = humanize_schedule("0 9 * * 1-5")
        assert label == "weekdays at 9:00 AM"

    def test_sub_hourly_slash(self):
        label, sub = humanize_schedule("*/15 * * * *")
        assert sub is True
        assert "15" in label

    def test_every_minute(self):
        _, sub = humanize_schedule("* * * * *")
        assert sub is True

    def test_fallback_to_raw(self):
        label, sub = humanize_schedule("0 8 1 1 *")
        assert "0 8 1 1 *" in label
        assert sub is False


class TestExtractCodeDailyCommand:
    def test_simple(self):
        assert extract_code_daily_command("code-daily news digest") == "news digest"

    def test_with_path_prefix(self):
        cmd = "cd /repo && PATH=/repo/.venv/bin:$PATH code-daily check 1"
        assert extract_code_daily_command(cmd) == "check 1"

    def test_with_flag(self):
        assert extract_code_daily_command("code-daily news digest --json") == "news digest"

    def test_missing(self):
        assert extract_code_daily_command("echo hello") == ""


class TestClassifyCommand:
    def test_ready(self):
        status, _ = classify_command("issues list")
        assert status == "ready"

    def test_blocked_check(self):
        status, _ = classify_command("check 1")
        assert status == "blocked"

    def test_blocked_notify(self):
        status, _ = classify_command("notify status")
        assert status == "blocked"

    def test_needs_refactor_news_digest(self):
        status, reason = classify_command("news digest")
        assert status == "needs_refactor"
        assert "vault" in reason.lower()

    def test_unknown_command(self):
        status, reason = classify_command("totally-fake-command")
        assert status == "needs_refactor"
        assert "COMMAND_RULES" in reason

    def test_empty_command(self):
        status, _ = classify_command("")
        assert status == "needs_refactor"

    def test_longest_prefix_wins(self):
        status, _ = classify_command("quests discover")
        assert status == "ready"


class TestBuildRoutinePrompt:
    def test_contains_schedule_and_command(self):
        prompt = build_routine_prompt("issues list", "daily at 8:00 AM")
        assert prompt.startswith("/schedule")
        assert "daily at 8:00 AM" in prompt
        assert "code-daily issues list" in prompt


class TestBuildPlan:
    def test_default_cron_entries(self):
        from src.main import _get_cron_entries

        plan = build_plan(_get_cron_entries())
        # Default schedule has 1 news digest + 4 check levels
        assert plan.summary["total"] == 5
        assert plan.summary["blocked"] == 4  # four check entries
        assert plan.summary["needs_refactor"] == 1  # news digest
        assert plan.summary["ready"] == 0

    def test_cloud_safe_entry(self):
        cron = "0 9 * * * code-daily issues list --json"
        plan = build_plan(cron)
        assert plan.summary["ready"] == 1
        assert plan.entries[0].routine_prompt is not None

    def test_sub_hourly_is_blocked(self):
        cron = "*/10 * * * * code-daily issues list"
        plan = build_plan(cron)
        assert plan.entries[0].status == "blocked"
        assert "1-hour" in plan.entries[0].reason

    def test_to_dict_includes_docs_url(self):
        plan = build_plan("0 8 * * * code-daily issues list")
        d = plan.to_dict()
        assert d["routines_docs_url"] == ROUTINES_DOCS_URL
        assert "summary" in d and "entries" in d


class TestRenderMigrationGuide:
    def test_emits_summary_counts(self):
        from src.main import _get_cron_entries

        plan = build_plan(_get_cron_entries())
        md = render_migration_guide_md(plan, "2026-04-14")
        assert "# code-daily" in md
        assert "Summary" in md
        assert "Ready to migrate" in md
        assert ROUTINES_DOCS_URL in md

    def test_includes_ready_prompts_when_present(self):
        plan = build_plan("0 9 * * * code-daily issues list --json")
        md = render_migration_guide_md(plan, "2026-04-14")
        assert "/schedule" in md
        assert "Ready-to-paste" in md

    def test_no_ready_section_when_none_ready(self):
        plan = build_plan("0 8 * * * code-daily check 1")
        md = render_migration_guide_md(plan, "2026-04-14")
        assert "Ready-to-paste" not in md
        assert "Blocked" in md
