"""
Circle-back: earmark items to revisit later.

A lightweight backlog for things you want to come back to but can't (or don't
want to) act on right now — work you started and mean to continue, new project
ideas worth retaining, or anything surfaced during a `/newsandideas` run that's
worth more than a fleeting mention.

It is deliberately distinct from the two neighbouring systems:

* ``quests`` is the *prioritized work queue* fed by automated discovery sources.
* ``ideas`` is the IDEAS.md-backed running list of coding ideas.

Circle-back items add two things neither has: an optional **snooze-until date**
(``circle_back_date``) so an item stays quiet until it's due, and an explicit
**priority** that signals to the agent what you think is important. Items can be
promoted into a real GitHub issue once they're ready to act on.
"""

from datetime import date, datetime

from src.storage import CommitStorage

# Kinds map to the three buckets the feature is for.
VALID_KINDS = ("continue", "project", "idea")
DEFAULT_KIND = "idea"

# Priority is stored as an int (1 = high) so it sorts naturally, but exposed to
# humans as words.
PRIORITY_BY_NAME = {"high": 1, "medium": 2, "low": 3}
PRIORITY_NAME = {1: "high", 2: "medium", 3: "low"}
DEFAULT_PRIORITY = 2

VALID_STATUSES = ("open", "done", "promoted", "dropped")


class CircleBackError(ValueError):
    """Raised when a circle-back item is created/updated with invalid input."""


def parse_priority(value) -> int:
    """Normalise a priority given as a word ('high') or int (1) to an int.

    Raises CircleBackError on anything unrecognised.
    """
    if value is None:
        return DEFAULT_PRIORITY
    if isinstance(value, int):
        if value in PRIORITY_NAME:
            return value
        raise CircleBackError(f"priority must be 1-3, got {value}")
    text = str(value).strip().lower()
    if text in PRIORITY_BY_NAME:
        return PRIORITY_BY_NAME[text]
    if text in {"1", "2", "3"}:
        return int(text)
    raise CircleBackError(
        f"priority must be one of high/medium/low or 1-3, got {value!r}"
    )


def _validate_kind(kind: str) -> str:
    kind = (kind or DEFAULT_KIND).strip().lower()
    if kind not in VALID_KINDS:
        raise CircleBackError(
            f"kind must be one of {', '.join(VALID_KINDS)}, got {kind!r}"
        )
    return kind


def _validate_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise CircleBackError(
            f"circle_back_date must be YYYY-MM-DD, got {value!r}"
        ) from exc
    return value


def _decorate(item: dict) -> dict:
    """Add human-friendly derived fields to a raw item dict."""
    if item is None:
        return item
    item = dict(item)
    item["priority_label"] = PRIORITY_NAME.get(item.get("priority"), "medium")
    return item


class CircleBackManager:
    """Operations over the circle-back backlog."""

    def __init__(self, storage: CommitStorage | None = None):
        self.storage = storage or CommitStorage()

    # -- create / mutate ---------------------------------------------------

    def add(
        self,
        content: str,
        kind: str = DEFAULT_KIND,
        priority=DEFAULT_PRIORITY,
        circle_back_date: str | None = None,
        note: str | None = None,
        source: str = "manual",
        source_ref: str | None = None,
    ) -> dict:
        """Add an item to the backlog. Deduplicates on (source, source_ref).

        Returns the created (or pre-existing, for a duplicate) item dict.
        """
        content = (content or "").strip()
        if not content:
            raise CircleBackError("content must not be empty")

        kind = _validate_kind(kind)
        priority_int = parse_priority(priority)
        circle_back_date = _validate_date(circle_back_date)

        if source_ref and self.storage.circleback_exists_by_source_ref(
            source, source_ref
        ):
            # Return the existing item rather than creating a duplicate.
            for existing in self.storage.get_circleback_items():
                if existing.get("source") == source and existing.get(
                    "source_ref"
                ) == source_ref:
                    return _decorate(existing)

        item_id = self.storage.create_circleback_item(
            content=content,
            kind=kind,
            priority=priority_int,
            circle_back_date=circle_back_date,
            note=note,
            source=source,
            source_ref=source_ref,
        )
        return _decorate(self.storage.get_circleback_item(item_id))

    def mark_done(self, item_id: int) -> bool:
        return self.storage.update_circleback_status(item_id, "done")

    def drop(self, item_id: int) -> bool:
        return self.storage.update_circleback_status(item_id, "dropped")

    def snooze(self, item_id: int, circle_back_date: str) -> bool:
        """Set/replace the snooze-until date on an item."""
        circle_back_date = _validate_date(circle_back_date)
        return self.storage.update_circleback_fields(
            item_id, circle_back_date=circle_back_date or ""
        )

    def set_priority(self, item_id: int, priority) -> bool:
        return self.storage.update_circleback_fields(
            item_id, priority=parse_priority(priority)
        )

    # -- read --------------------------------------------------------------

    def list_items(
        self, status: str | None = "open", kind: str | None = None
    ) -> list[dict]:
        items = self.storage.get_circleback_items(status=status, kind=kind)
        return [_decorate(i) for i in items]

    def get(self, item_id: int) -> dict | None:
        return _decorate(self.storage.get_circleback_item(item_id))

    def due_items(self, today: date | None = None) -> list[dict]:
        """Open items that are due now: undated, or dated on/before today.

        These are the items worth surfacing — the rest are still snoozed.
        """
        today = today or date.today()
        cutoff = today.isoformat()
        due = []
        for item in self.list_items(status="open"):
            cbd = item.get("circle_back_date")
            if not cbd or cbd <= cutoff:
                due.append(item)
        return due

    def upcoming_items(self, today: date | None = None) -> list[dict]:
        """Open items still snoozed for a future date."""
        today = today or date.today()
        cutoff = today.isoformat()
        return [
            item
            for item in self.list_items(status="open")
            if item.get("circle_back_date") and item["circle_back_date"] > cutoff
        ]

    # -- GitHub bridge -----------------------------------------------------

    def promote_to_issue(self, item_id: int, repo: str | None = None) -> dict:
        """Create a GitHub issue from an item and mark it 'promoted'.

        Returns a result dict: {"ok": bool, "item": ..., "issue_url"/"error": ...}.
        """
        from src.gh_issues import create_issue

        item = self.storage.get_circleback_item(item_id)
        if not item:
            return {"ok": False, "error": f"circle-back item {item_id} not found"}

        body_lines = []
        if item.get("note"):
            body_lines.append(item["note"])
        meta = (
            f"\n\n---\n_Earmarked via code-daily circle-back "
            f"(kind: {item.get('kind')}, priority: "
            f"{PRIORITY_NAME.get(item.get('priority'), 'medium')})._"
        )
        body = ("\n".join(body_lines) + meta).strip()

        result = create_issue(title=item["content"], body=body, repo=repo)
        if not result.get("created"):
            return {"ok": False, "error": result.get("error", "issue creation failed")}

        url = result.get("url", "")
        self.storage.set_circleback_issue(item_id, url)
        return {
            "ok": True,
            "issue_url": url,
            "item": _decorate(self.storage.get_circleback_item(item_id)),
        }

    # -- agent surfacing ---------------------------------------------------

    def build_agent_context(self, today: date | None = None) -> dict:
        """Structured context for the /newsandideas pipeline.

        Surfaces the due backlog grouped by kind plus a count of what's still
        snoozed, so the agent knows what the user has flagged as important
        before proposing new work.
        """
        due = self.due_items(today=today)
        by_kind: dict[str, list[dict]] = {k: [] for k in VALID_KINDS}
        for item in due:
            by_kind.setdefault(item.get("kind", DEFAULT_KIND), []).append(item)

        upcoming = self.upcoming_items(today=today)
        return {
            "due": due,
            "due_count": len(due),
            "by_kind": by_kind,
            "upcoming_count": len(upcoming),
            "summary": self._summary_line(due, upcoming),
        }

    @staticmethod
    def _summary_line(due: list[dict], upcoming: list[dict]) -> str:
        if not due and not upcoming:
            return "No circle-back items flagged."
        high = sum(1 for i in due if i.get("priority") == 1)
        parts = [f"{len(due)} item(s) to circle back to"]
        if high:
            parts.append(f"{high} high-priority")
        if upcoming:
            parts.append(f"{len(upcoming)} still snoozed")
        return ", ".join(parts) + "."
