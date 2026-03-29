"""
Text-to-speech podcast generation from synthesized news digests.

Reads a synthesized digest from the Obsidian vault, converts it to a
natural speech script, and generates an MP3 using edge-tts.
"""

import asyncio
import os
import re
from datetime import date, datetime


DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"


def read_synthesis_from_vault(vault_path: str, date_str: str) -> dict:
    """Read a synthesized digest markdown file and parse it back into a synthesis dict.

    Raises FileNotFoundError if the file doesn't exist.
    Raises ValueError if the file is not a synthesized digest.
    """
    file_path = os.path.join(vault_path, "ai-news", f"{date_str}.md")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No digest found for {date_str} at {file_path}")

    with open(file_path) as f:
        content = f.read()

    # Check for synthesized tag in frontmatter
    frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not frontmatter_match:
        raise ValueError(f"No frontmatter found in {file_path}")

    frontmatter = frontmatter_match.group(1)
    if "synthesized" not in frontmatter:
        raise ValueError(f"Digest for {date_str} is not a synthesized digest")

    # Parse body after frontmatter
    body = content[frontmatter_match.end():].strip()

    overview = ""
    sections = []
    current_section = None

    for line in body.split("\n"):
        # Skip the H1 title
        if line.startswith("# "):
            continue

        if line.startswith("## Overview"):
            current_section = "__overview__"
            continue

        if line.startswith("## ") and current_section != "__overview__" or (
            line.startswith("## ") and current_section == "__overview__" and overview
        ):
            # New section
            section_name = line[3:].strip()
            current_section = section_name
            sections.append({
                "name": section_name,
                "slug": re.sub(r"[^a-z0-9]+", "-", section_name.lower()).strip("-"),
                "summary": "",
                "items": [],
            })
            continue

        if current_section == "__overview__":
            if line.strip():
                overview = line.strip()
            continue

        if not sections:
            continue

        sec = sections[-1]

        # Parse bullet items: - [title](url) (Source, Npts) — commentary
        item_match = re.match(
            r"^- \[(.+?)\]\((.+?)\)\s*(?:\(([^)]*)\))?\s*(?:—\s*(.*))?$",
            line,
        )
        if item_match:
            title = item_match.group(1)
            url = item_match.group(2)
            meta = item_match.group(3) or ""
            commentary = item_match.group(4) or ""

            # Parse source and score from meta like "Reddit, 719pts"
            source = ""
            score = 0
            if meta:
                meta_parts = [p.strip() for p in meta.split(",")]
                for part in meta_parts:
                    pts_match = re.match(r"(\d+)pts", part)
                    if pts_match:
                        score = int(pts_match.group(1))
                    else:
                        source = part

            sec["items"].append({
                "title": title,
                "url": url,
                "source": source,
                "score": score,
                "commentary": commentary.strip(),
            })
            continue

        # Non-item, non-empty line is the section summary
        if line.strip() and not sec["summary"]:
            sec["summary"] = line.strip()

    return {
        "overview": overview,
        "sections": sections,
    }


def digest_to_script(synthesis: dict, date_str: str = "") -> str:
    """Convert a synthesis dict into natural spoken text for TTS.

    Strips URLs, markdown formatting, and score metadata.
    """
    parts = []

    # Intro with natural date
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            natural_date = dt.strftime("%B %-d, %Y")
        except ValueError:
            natural_date = date_str
    else:
        natural_date = date.today().strftime("%B %-d, %Y")

    parts.append(f"Here is your AI news digest for {natural_date}.")
    parts.append("")

    # Overview
    overview = synthesis.get("overview", "")
    if overview:
        parts.append(overview)
        parts.append("")

    # Sections
    sections = synthesis.get("sections", [])
    for i, section in enumerate(sections):
        name = section.get("name", "")
        summary = section.get("summary", "")
        items = section.get("items", [])

        if i == 0:
            parts.append(f"Starting with {name}.")
        elif i == len(sections) - 1:
            parts.append(f"Finally, {name}.")
        else:
            parts.append(f"Moving on to {name}.")

        if summary:
            parts.append(summary)

        parts.append("")

        for item in items:
            title = item.get("title", "")
            commentary = item.get("commentary", "")

            if commentary:
                parts.append(f"{title}. {commentary}")
            else:
                parts.append(f"{title}.")

        parts.append("")

    # Outro
    parts.append("That wraps up today's AI news digest. Have a productive day.")

    return "\n".join(parts)


def generate_podcast(
    script: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
) -> str:
    """Generate an MP3 podcast from a text script using edge-tts.

    Returns the output file path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    asyncio.run(_generate_audio(script, output_path, voice))
    return output_path


async def _generate_audio(text: str, output_path: str, voice: str) -> None:
    """Internal async function to call edge-tts."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def write_podcast_to_vault(
    vault_path: str,
    date_str: str,
    script: str,
    voice: str = DEFAULT_VOICE,
) -> dict:
    """Generate a podcast and save it to the Obsidian vault.

    Returns metadata dict with file path and details.
    """
    rel_path = f"ai-news/podcasts/{date_str}.mp3"
    full_path = os.path.join(vault_path, rel_path)

    generate_podcast(script, full_path, voice)

    return {
        "date": date_str,
        "vault_file": rel_path,
        "voice": voice,
        "script_length": len(script),
        "audio_path": full_path,
    }
