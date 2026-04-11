"""Tests for beacon skill gap quest sync."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.storage import CommitStorage


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = CommitStorage(str(db_path))
    return s


SAMPLE_GAPS = [
    {
        "title": "[beacon-gap] Learn Kafka (5 jobs require it)",
        "source": "beacon_gap",
        "source_ref": "beacon_gap:kafka",
        "description": "Skill gap: 5 of your top job matches require Kafka.",
        "skill_name": "Kafka",
        "demand_count": 5,
    },
    {
        "title": "[beacon-gap] Learn JavaScript (3 jobs require it)",
        "source": "beacon_gap",
        "source_ref": "beacon_gap:javascript",
        "description": "Skill gap: 3 of your top job matches require JavaScript.",
        "skill_name": "JavaScript",
        "demand_count": 3,
    },
]


class TestBeaconGapQuestCreation:
    def test_creates_quests_from_gaps(self, storage):
        for gap in SAMPLE_GAPS:
            storage.create_quest(
                title=gap["title"],
                source="beacon_gap",
                source_ref=gap["source_ref"],
                description=gap["description"],
            )

        quests = storage.get_quests(status="pending")
        beacon_quests = [q for q in quests if q["source"] == "beacon_gap"]
        assert len(beacon_quests) == 2

    def test_deduplication(self, storage):
        gap = SAMPLE_GAPS[0]
        storage.create_quest(
            title=gap["title"],
            source="beacon_gap",
            source_ref=gap["source_ref"],
            description=gap["description"],
        )

        assert storage.quest_exists_by_source_ref("beacon_gap", "beacon_gap:kafka") is True
        assert storage.quest_exists_by_source_ref("beacon_gap", "beacon_gap:nonexistent") is False

    def test_quest_has_correct_fields(self, storage):
        gap = SAMPLE_GAPS[0]
        quest_id = storage.create_quest(
            title=gap["title"],
            source="beacon_gap",
            source_ref=gap["source_ref"],
            description=gap["description"],
        )

        quest = storage.get_quest(quest_id)
        assert quest["title"] == "[beacon-gap] Learn Kafka (5 jobs require it)"
        assert quest["source"] == "beacon_gap"
        assert quest["source_ref"] == "beacon_gap:kafka"
        assert "Kafka" in quest["description"]
        assert quest["status"] == "pending"


class TestBeaconGapPriority:
    def test_beacon_gap_has_highest_source_priority(self):
        from src.quest_manager import QuestManager

        qm = QuestManager.__new__(QuestManager)
        beacon_quest = {"source": "beacon_gap", "created_at": "2026-01-01T00:00:00"}
        external_quest = {"source": "external", "created_at": "2026-01-01T00:00:00"}

        beacon_score = qm.calculate_priority_score(beacon_quest)
        external_score = qm.calculate_priority_score(external_quest)
        assert beacon_score > external_score
