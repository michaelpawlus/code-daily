"""
Analyze suggestion diversity over time.

Reads the suggestion_log table and computes a diversity score (0-100)
based on domain spread, source balance, repetition, and recency.
"""

from collections import Counter


def compute_diversity_score(storage, days: int = 14) -> dict:
    """Analyze suggestion diversity over a time window.

    Args:
        storage: CommitStorage instance with suggestion_log methods.
        days: Number of days to analyze.

    Returns:
        Dict with score, rating, breakdowns, and optional warning.
    """
    suggestions = storage.get_recent_suggestions(days=days)
    total = len(suggestions)

    if total == 0:
        return {
            "score": 0.0,
            "rating": "no data",
            "unique_domains": 0,
            "total_suggestions": 0,
            "domain_spread": 0.0,
            "source_spread": {},
            "most_repeated": [],
            "underrepresented_domains": [],
            "days_analyzed": days,
            "warning": "No suggestions logged yet. Run 'code-daily suggest' to start tracking.",
        }

    # Domain analysis
    domains = [s["domain"] for s in suggestions if s.get("domain")]
    unique_domains = len(set(domains))
    domain_counts = Counter(domains)

    # Source analysis
    source_counts = Counter(s["source"] for s in suggestions)

    # Repetition analysis (by content_hash)
    hash_counts = Counter(s["content_hash"] for s in suggestions)
    most_repeated = [
        {"title": _find_title_for_hash(suggestions, h), "count": c}
        for h, c in hash_counts.most_common(3)
        if c > 1
    ]

    # Recency: check if any new domain appeared in last 3 days
    recent = storage.get_recent_suggestions(days=3)
    recent_domains = {s["domain"] for s in recent if s.get("domain")}
    older_domains = {s["domain"] for s in suggestions if s.get("domain")} - recent_domains
    has_new_recent_domain = bool(recent_domains - (set(domains) - recent_domains))

    # Known project domains for "underrepresented" check
    all_known_domains = storage.get_recent_suggestion_domains(days=90)
    recent_30 = set(storage.get_recent_suggestion_domains(days=days))
    underrepresented = [d for d in all_known_domains if d not in recent_30]

    # Scoring
    # Domain spread (0-40)
    domain_score = min(40.0, (unique_domains / max(total, 1)) * 40) if total > 0 else 0

    # Source balance (0-20): penalize if >80% from one source
    source_balance = 20.0
    if source_counts:
        max_source_pct = max(source_counts.values()) / total
        if max_source_pct > 0.8:
            source_balance = max(0, 20 - (max_source_pct - 0.8) * 100)

    # Repetition penalty (0-20)
    avg_repeats = sum(hash_counts.values()) / len(hash_counts) if hash_counts else 1
    repetition_score = max(0.0, 20 - (avg_repeats - 1) * 5)

    # Recency bonus (0-20)
    recency_score = 20.0 if has_new_recent_domain else 5.0

    score = round(domain_score + source_balance + repetition_score + recency_score, 1)

    if score >= 70:
        rating = "high"
    elif score >= 40:
        rating = "moderate"
    else:
        rating = "low"

    warning = None
    if rating == "low":
        warning = "Ideas are converging — consider exploring new domains or sources."
    elif rating == "moderate" and not has_new_recent_domain:
        warning = "No new domains in the last 3 days — try branching out."

    return {
        "score": score,
        "rating": rating,
        "unique_domains": unique_domains,
        "total_suggestions": total,
        "domain_spread": round(unique_domains / max(total, 1), 2),
        "source_spread": dict(source_counts),
        "most_repeated": most_repeated,
        "underrepresented_domains": underrepresented[:5],
        "days_analyzed": days,
        "warning": warning,
    }


def _find_title_for_hash(suggestions: list[dict], content_hash: str) -> str:
    """Find the title for a given content_hash."""
    for s in suggestions:
        if s["content_hash"] == content_hash:
            return s["title"]
    return ""
