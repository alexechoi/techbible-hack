from __future__ import annotations

import logging
import os

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)

BRIGHT_DATA_API_TOKEN = os.getenv(
    "BRIGHT_DATA_API_TOKEN",
    "",
)
MCP_BASE_URL = "https://mcp.brightdata.com/sse"


def _build_url(token: str | None = None) -> str:
    t = token or BRIGHT_DATA_API_TOKEN
    if not t:
        raise ValueError("BRIGHT_DATA_API_TOKEN is not set")
    return f"{MCP_BASE_URL}?token={t}"


async def scrape_url(url: str, token: str | None = None) -> str:
    """Scrape a single URL via Bright Data MCP and return the markdown content."""
    mcp_url = _build_url(token)
    logger.info("MCP scrape request: %s", url)

    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "scrape_as_markdown",
                {"url": url},
            )
            if result.isError:
                error_text = result.content[0].text if result.content else "Unknown MCP error"
                logger.error("MCP scrape error for %s: %s", url, error_text)
                raise RuntimeError(f"MCP scrape failed: {error_text}")

            text = result.content[0].text if result.content else ""
            logger.info("MCP scrape success for %s (%d chars)", url, len(text))
            return text
