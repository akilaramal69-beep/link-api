"""
extractor.py — Orchestrates two extraction strategies:
  1. Playwright browser interception (IDM-style) — works on ANY site
  2. yt-dlp — fallback and enrichment for known platforms

Strategy:
  - If use_browser=True, try Playwright first
  - ALWAYS try yt-dlp as well (as fallback/enrichment)
  - Merge and deduplicate results from both
  - Raise only if BOTH fail
"""

import asyncio
import yt_dlp
from typing import Optional
from browser_extractor import intercept_browser


async def extract_links(url: str, use_browser: bool = True, timeout: int = 25) -> dict:
    browser_results = []
    ytdlp_result = None
    errors = []

    # ── Strategy 1: Headless browser interception ──────────────────────────────
    if use_browser:
        try:
            browser_results = await intercept_browser(url, timeout_ms=timeout * 1000)
        except Exception as e:
            errors.append(f"browser_error: {e}")

    # ── Strategy 2: yt-dlp (always attempted as fallback / enrichment) ─────────
    try:
        loop = asyncio.get_event_loop()
        ytdlp_result = await loop.run_in_executor(None, _ytdlp_extract, url)
    except Exception as e:
        errors.append(f"ytdlp_error: {e}")

    if not browser_results and ytdlp_result is None:
        raise RuntimeError(
            f"Could not extract any links. Details — {'; '.join(errors)}"
        )

    # ── Build unified response ─────────────────────────────────────────────────
    response: dict = {
        "url": url,
        "title": None,
        "thumbnail": None,
        "duration": None,
        "extractor": None,
        "uploader": None,
    }

    if ytdlp_result:
        response["title"] = ytdlp_result.get("title")
        response["thumbnail"] = ytdlp_result.get("thumbnail")
        response["duration"] = ytdlp_result.get("duration")
        response["extractor"] = ytdlp_result.get("extractor")
        response["uploader"] = ytdlp_result.get("uploader")

    # Merge browser links + yt-dlp formats
    all_links = list(browser_results)

    if ytdlp_result:
        for fmt in ytdlp_result.get("formats", []):
            if not fmt.get("url"):
                continue
            all_links.append({
                "url": fmt["url"],
                "stream_type": _guess_type_ytdlp(fmt),
                "content_type": fmt.get("ext"),
                "height": fmt.get("height"),
                "fps": fmt.get("fps"),
                "tbr": fmt.get("tbr"),
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                "format_note": fmt.get("format_note"),
                "has_video": fmt.get("vcodec", "none") != "none",
                "has_audio": fmt.get("acodec", "none") != "none",
                "source": "ytdlp",
            })

    # Deduplicate by URL
    seen = set()
    unique_links = []
    for link in all_links:
        u = link["url"]
        if u not in seen:
            seen.add(u)
            unique_links.append(link)

    # Sort: combined streams first, then by height
    unique_links.sort(
        key=lambda x: (
            bool(x.get("has_video") and x.get("has_audio")),
            x.get("height") or 0,
        ),
        reverse=True,
    )

    response["links"] = unique_links
    response["total"] = len(unique_links)
    response["best_link"] = _pick_best(unique_links)
    response["errors"] = errors if errors else None

    return response


def _ytdlp_extract(url: str) -> Optional[dict]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "age_limit": 99,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _guess_type_ytdlp(fmt: dict) -> str:
    ext = fmt.get("ext", "").lower()
    vcodec = fmt.get("vcodec", "none")
    acodec = fmt.get("acodec", "none")
    if ext in ("m3u8", "m3u"):
        return "hls"
    if ext == "mpd":
        return "dash"
    if vcodec != "none" and acodec != "none":
        return "video+audio"
    if vcodec != "none":
        return "video"
    if acodec != "none":
        return "audio"
    return ext or "unknown"


def _pick_best(links: list) -> Optional[str]:
    if not links:
        return None
    for link in links:
        if link.get("stream_type") == "hls":
            return link["url"]
    for link in links:
        if link.get("has_video") and link.get("has_audio"):
            return link["url"]
    for link in links:
        if link.get("stream_type") == "mp4":
            return link["url"]
    return links[0]["url"]


async def extract_raw_ytdlp(url: str) -> dict:
    """Run yt-dlp on the URL and return the raw info dict untouched."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _ytdlp_extract, url)
    if not result:
        raise ValueError(f"No info extracted for {url}")
    return result
