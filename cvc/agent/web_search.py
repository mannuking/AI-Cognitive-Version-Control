"""
cvc.agent.web_search — Web search capability for the CVC agent.

Provides a /web command and web_search tool that lets the agent
search the web for documentation, API references, Stack Overflow
answers, and other external knowledge.

Uses DuckDuckGo HTML search (no API key required) as the default backend.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("cvc.agent.web_search")

# DuckDuckGo HTML endpoint — no API key needed
DDG_URL = "https://html.duckduckgo.com/html/"

MAX_RESULTS = 8
MAX_SNIPPET_LEN = 300
SEARCH_TIMEOUT = 15


async def web_search(query: str, max_results: int = MAX_RESULTS) -> list[dict[str, str]]:
    """
    Search the web using DuckDuckGo HTML and return results.

    Returns a list of dicts with 'title', 'url', 'snippet'.
    """
    results: list[dict[str, str]] = []

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.post(
                DDG_URL,
                data={"q": query, "b": ""},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CVC-Agent/1.0)",
                },
            )

            if resp.status_code != 200:
                logger.warning("DuckDuckGo search returned status %d", resp.status_code)
                return []

            body = resp.text

            # Parse results from HTML (lightweight, no deps)
            result_blocks = re.findall(
                r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'class="result__snippet"[^>]*>(.*?)</(?:td|div|span)',
                body,
                re.DOTALL,
            )

            for url, title_html, snippet_html in result_blocks[:max_results]:
                title = _strip_html(title_html).strip()
                snippet = _strip_html(snippet_html).strip()

                # Clean up DuckDuckGo redirect URLs
                if "uddg=" in url:
                    match = re.search(r'uddg=([^&]+)', url)
                    if match:
                        from urllib.parse import unquote
                        url = unquote(match.group(1))

                if title and url:
                    results.append({
                        "title": title[:200],
                        "url": url,
                        "snippet": snippet[:MAX_SNIPPET_LEN],
                    })

    except httpx.TimeoutException:
        logger.warning("Web search timed out for query: %s", query)
    except Exception as e:
        logger.warning("Web search failed: %s", e)

    return results


async def fetch_page_text(url: str, max_chars: int = 5000) -> str:
    """
    Fetch a web page and return its text content (stripped of HTML tags).
    """
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CVC-Agent/1.0)",
                },
            )

            if resp.status_code != 200:
                return f"Failed to fetch page: HTTP {resp.status_code}"

            text = _strip_html(resp.text)
            # Clean up excessive whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)

            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n... (truncated)"

            return text.strip()

    except httpx.TimeoutException:
        return "Failed to fetch page: timeout"
    except Exception as e:
        return f"Failed to fetch page: {e}"


def format_search_results(results: list[dict[str, str]], query: str) -> str:
    """Format search results for display."""
    if not results:
        return f"No web results found for: {query}"

    lines = [f"Web search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        lines.append("")

    return "\n".join(lines)


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return text.strip()
