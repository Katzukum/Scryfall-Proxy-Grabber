"""Shared HTTP client configuration for Scryfall requests."""

import httpx

from src.app_version import APP_VERSION


SCRYFALL_USER_AGENT = f"ProxyToolBox/{APP_VERSION}"


def create_scryfall_client(timeout: float) -> httpx.AsyncClient:
    """Create an HTTP client that identifies ProxyToolBox to Scryfall."""
    return httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": SCRYFALL_USER_AGENT},
    )
