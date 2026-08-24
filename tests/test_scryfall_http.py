import asyncio

from src.app_version import APP_VERSION
from src.scryfall_http import SCRYFALL_USER_AGENT, create_scryfall_client


def test_scryfall_client_uses_application_user_agent():
    client = create_scryfall_client(timeout=10.0)
    try:
        assert SCRYFALL_USER_AGENT == f"ProxyToolBox/{APP_VERSION}"
        assert client.headers["User-Agent"] == SCRYFALL_USER_AGENT
    finally:
        asyncio.run(client.aclose())
