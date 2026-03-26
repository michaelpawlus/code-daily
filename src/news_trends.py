"""
Analyze trending topics across news digest files in the Obsidian vault.

Reads ai-news/*.md files, extracts item titles from markdown,
and identifies topics that recur across multiple days.
"""

import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

# Common English stopwords + AI-news noise words
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "this", "that", "these",
    "those", "it", "its", "i", "you", "he", "she", "we", "they", "my",
    "your", "his", "her", "our", "their", "what", "which", "who", "whom",
    "how", "when", "where", "why", "not", "no", "so", "if", "than",
    "too", "very", "just", "about", "up", "out", "all", "as", "into",
    "more", "some", "any", "each", "every", "own", "other", "new",
    "now", "here", "there", "then", "also", "over", "after", "before",
    "between", "under", "through", "during", "without", "again",
    # AI-news noise
    "show", "hn", "ask", "tell", "says", "said", "using", "used",
    "built", "building", "makes", "made", "gets", "got", "vs", "via",
    "need", "want", "think", "like", "still", "yet", "much", "many",
    "most", "best", "first", "last", "next", "one", "two", "will",
    "anyone", "really", "actually", "already", "going",
    "d", "r", "n", "p",  # reddit flair prefixes
}

# Minimum word length to consider
_MIN_WORD_LEN = 3


def analyze_trends(vault_path: str, days: int = 30) -> dict:
    """Scan vault digest files and identify trending topics.

    Args:
        vault_path: Path to the Obsidian vault root.
        days: How many days back to analyze.

    Returns:
        Dict with trending topics, new_today, fading topics.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    digest_dir = os.path.join(vault_path, "ai-news")

    if not os.path.isdir(digest_dir):
        return {
            "digests_analyzed": 0,
            "date_range": {"from": cutoff, "to": date.today().isoformat()},
            "trending": [],
            "new_today": [],
            "fading": [],
        }

    # Collect titles per date
    date_titles: dict[str, list[str]] = {}
    for filename in sorted(os.listdir(digest_dir)):
        if not filename.endswith(".md"):
            continue
        file_date = filename.replace(".md", "")
        if file_date < cutoff:
            continue
        filepath = os.path.join(digest_dir, filename)
        titles = _parse_digest_titles(filepath)
        if titles:
            date_titles[file_date] = titles

    if not date_titles:
        return {
            "digests_analyzed": 0,
            "date_range": {"from": cutoff, "to": date.today().isoformat()},
            "trending": [],
            "new_today": [],
            "fading": [],
        }

    sorted_dates = sorted(date_titles.keys())
    latest_date = sorted_dates[-1]

    # Extract topics per day
    date_topics: dict[str, set[str]] = {}
    topic_titles: dict[str, list[str]] = defaultdict(list)

    for d, titles in date_titles.items():
        topics_for_day = set()
        for title in titles:
            extracted = _extract_topics(title)
            for topic in extracted:
                topics_for_day.add(topic)
                topic_titles[topic].append(title)
        date_topics[d] = topics_for_day

    # Count how many days each topic appeared
    topic_day_count: Counter = Counter()
    topic_dates: dict[str, list[str]] = defaultdict(list)
    for d, topics in date_topics.items():
        for topic in topics:
            topic_day_count[topic] += 1
            topic_dates[topic].append(d)

    # Trending: topics appearing on 2+ days
    trending = []
    for topic, day_count in topic_day_count.most_common():
        if day_count < 2:
            break
        examples = list(dict.fromkeys(topic_titles[topic]))[:3]  # unique, up to 3
        trending.append({
            "topic": topic,
            "day_count": day_count,
            "total_mentions": len(topic_titles[topic]),
            "dates": sorted(topic_dates[topic]),
            "example_titles": examples,
        })

    # New today: topics only in latest digest
    latest_topics = date_topics.get(latest_date, set())
    older_topics = set()
    for d, topics in date_topics.items():
        if d != latest_date:
            older_topics |= topics
    new_today = sorted(latest_topics - older_topics)

    # Fading: topics in older digests but not in the latest
    fading = sorted(older_topics - latest_topics)
    # Only show meaningful ones (appeared on 2+ days before)
    fading = [t for t in fading if topic_day_count[t] >= 2]

    return {
        "digests_analyzed": len(date_titles),
        "date_range": {"from": sorted_dates[0], "to": sorted_dates[-1]},
        "trending": trending,
        "new_today": new_today[:20],
        "fading": fading[:10],
    }


def _parse_digest_titles(filepath: str) -> list[str]:
    """Extract item titles from a vault digest markdown file.

    Parses markdown links [title](url) from list items and table rows.
    """
    titles = []
    link_pattern = re.compile(r"\[([^\]]+)\]\(https?://[^\)]+\)")

    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                # Skip frontmatter, headings, and empty lines
                if line.startswith("---") or line.startswith("#") or not line:
                    continue
                # Extract all markdown links from the line
                for match in link_pattern.finditer(line):
                    title = match.group(1)
                    # Skip very short titles or pipe-escaped table noise
                    if len(title) > 10:
                        titles.append(title.replace("\\|", "|"))
    except (OSError, UnicodeDecodeError):
        pass

    return titles


def _extract_topics(title: str) -> list[str]:
    """Extract significant topic terms from a title.

    Returns lowercased significant words and 2-word phrases.
    """
    # Clean the title
    clean = re.sub(r"[^\w\s\-]", " ", title.lower())
    words = clean.split()

    # Filter to significant words
    significant = [
        w for w in words
        if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS
    ]

    topics = []

    # Single significant words (tech terms, proper nouns, etc.)
    for word in significant:
        topics.append(word)

    # 2-word phrases from adjacent significant words
    for i in range(len(significant) - 1):
        phrase = f"{significant[i]} {significant[i+1]}"
        topics.append(phrase)

    return topics
