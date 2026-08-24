"""Parses Moxfield-style deck export text into structured CardEntry objects."""

import re

from src.models import CardEntry


# Matches: "1 Card Name (SET) 123" with optional trailing junk (foil markers, stars, etc.)
_CARD_PATTERN = re.compile(r"(\d+)\s+(.+?)\s+\((\w{2,5})\)\s+([\w\d-]+)")


def parse_deck_list(text_block: str) -> list[CardEntry]:
    """Parse a Moxfield-style deck export text block into CardEntry objects.

    Handles formatting variations and strips trailing non-alphanumeric junk
    (foil markers, stars, etc.) from each line before parsing.

    Args:
        text_block: Raw text block with one card per line.

    Returns:
        List of parsed CardEntry objects. Unparseable lines are silently skipped.
    """
    entries: list[CardEntry] = []

    for raw_line in text_block.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.casefold().rstrip(":") == "sideboard":
            continue

        # Strip trailing junk after the last digit sequence
        cleaned = _clean_trailing_junk(line)
        match = _CARD_PATTERN.match(cleaned)

        if match:
            quantity_str, name, set_code, collector_number = match.groups()
            entries.append(
                CardEntry(
                    quantity=int(quantity_str),
                    name=name.strip(),
                    set_code=set_code.lower(),
                    collector_number=collector_number,
                    raw_line=raw_line,
                )
            )

    return entries


def _clean_trailing_junk(line: str) -> str:
    """Remove non-alphanumeric trailing characters after the final number block.

    For example: '1 Venser, the Sojourner (SLD) 1423★ *F*' -> '1 Venser, the Sojourner (SLD) 1423'
    """
    last_number_end = -1
    for m in re.finditer(r"\d+", line):
        last_number_end = m.end()

    if last_number_end == -1:
        return line

    if last_number_end < len(line) and not line[last_number_end].isalnum() and line[last_number_end] not in ")-":
        return line[:last_number_end]

    return line
