"""Scryfall search client — fuzzy name search and set+collector lookup."""

import asyncio
from typing import Any

from src.models import CardSearchResult
from src.scryfall_http import create_scryfall_client


_RATE_LIMIT_SECONDS = 0.1


async def autocomplete_card_name(query: str) -> list[str]:
    """Get card name suggestions from Scryfall autocomplete.

    Args:
        query: Partial card name to search for.

    Returns:
        List of matching card name strings (up to 20).
    """
    if not query or len(query) < 2:
        return []

    async with create_scryfall_client(timeout=10.0) as client:
        await asyncio.sleep(_RATE_LIMIT_SECONDS)
        response = await client.get(
            "https://api.scryfall.com/cards/autocomplete",
            params={"q": query},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])


async def search_card_by_name(name: str) -> list[CardSearchResult]:
    """Search for cards by name and fetch all versions from Scryfall.

    Args:
        name: Card name or search query.

    Returns:
        List of CardSearchResult with image URLs and full JSON.
    """
    results = []
    # Search for all printings, with newest releases first.
    params = {
        "q": name,
        "unique": "prints",
        "order": "released",
    }

    async with create_scryfall_client(timeout=10.0) as client:
        url = "https://api.scryfall.com/cards/search"
        while url:
            await asyncio.sleep(_RATE_LIMIT_SECONDS)
            response = await client.get(url, params=params if url == "https://api.scryfall.com/cards/search" else None)
            
            if response.status_code == 404:
                break
                
            response.raise_for_status()
            data = response.json()
            
            for card in data.get("data", []):
                results.append(_card_to_result(card))
            
            if data.get("has_more"):
                url = data.get("next_page")
            else:
                url = None
                
    return results


async def lookup_card_by_set(set_code: str, collector_number: str) -> list[CardSearchResult]:
    """Fetch a specific card printing by set code and collector number.

    Args:
        set_code: Set code (e.g., 'mh2', 'dmu').
        collector_number: Collector number within the set.

    Returns:
        List with one CardSearchResult (for API consistency), or empty list if not found.
    """
    async with create_scryfall_client(timeout=10.0) as client:
        await asyncio.sleep(_RATE_LIMIT_SECONDS)
        response = await client.get(
            f"https://api.scryfall.com/cards/{set_code.lower()}/{collector_number}",
        )

        if response.status_code == 404:
            return []

        response.raise_for_status()
        card = response.json()
        return [_card_to_result(card)]


def _card_to_result(card: dict[str, Any]) -> CardSearchResult:
    """Convert a raw Scryfall card JSON into a CardSearchResult."""
    # Handle image URLs — handle double-faced cards
    image_url = ""
    image_url_small = ""
    
    if "image_uris" in card:
        image_url = card["image_uris"].get("normal", "")
        image_url_small = card["image_uris"].get("small", "")
    elif "card_faces" in card and card["card_faces"]:
        # Default to first face if multiple
        face = card["card_faces"][0]
        if "image_uris" in face:
            image_url = face["image_uris"].get("normal", "")
            image_url_small = face["image_uris"].get("small", "")

    return CardSearchResult(
        name=card.get("name", "Unknown"),
        set_code=card.get("set", "").upper(),
        collector_number=card.get("collector_number", ""),
        image_url=image_url,
        image_url_small=image_url_small,
        scryfall_uri=card.get("scryfall_uri", ""),
        raw_json=card,
    )
