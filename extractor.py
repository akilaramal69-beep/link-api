"""
extractor.py — Orchestrates two extraction strategies:
  1. Playwright browser interception (IDM-style) — works on ANY site
  2. yt-dlp fallback — for known platforms (YouTube, Twitter, etc.)

Strategy order:
  - Browser first → if it finds media links, return them
  - If browser finds nothing OR fails → try yt-dlp
  - If both fail → raise error
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
            errors.append(f"browser: {e}")

    # ── Strategy 2: yt-dlp ────────────────────────────────────────────────────
    # Always run yt-dlp if browser found nothing, or as enrichment for known sites
    if not browser_results or _is_known_platform(url):
        try:
            loop = asyncio.get_event_loop()
            ytdlp_result = await loop.run_in_executor(None, _ytdlp_extract, url)
        except Exception as e:
            errors.append(f"ytdlp: {e}")

    if not browser_results and ytdlp_result is None:
        raise RuntimeError(
            f"Could not extract links from this URL. Errors: {'; '.join(errors)}"
        )

    # ── Build unified response ─────────────────────────────────────────────────
    response: dict = {
        "url": url,
        "title": None,
        "thumbnail": None,
        "duration": None,
        "extractor": None,
    }

    # Populate metadata from yt-dlp if available
    if ytdlp_result:
        response["title"] = ytdlp_result.get("title")
        response["thumbnail"] = ytdlp_result.get("thumbnail")
        response["duration"] = ytdlp_result.get("duration")
        response["extractor"] = ytdlp_result.get("extractor")
        response["uploader"] = ytdlp_result.get("uploader")

    # Merge browser links + yt-dlp formats into one unified list
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

    # Sort: prefer combined streams, then by quality
    unique_links.sort(
        key=lambda x: (
            x.get("has_video") and x.get("has_audio"),
            x.get("height") or 0,
        ),
        reverse=True,
    )

    # Best picks
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
        info = ydl.extract_info(url, download=False)
    return info


def _is_known_platform(url: str) -> bool:
    known = (
        "youtube.com", "youtu.be", "twitter.com", "x.com",
        "instagram.com", "tiktok.com", "reddit.com", "facebook.com",
        "vimeo.com", "dailymotion.com", "twitch.tv",
    )
    return any(k in url.lower() for k in known)


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
    # Prefer HLS manifests (most universal)
    for link in links:
        if link.get("stream_type") == "hls":
            return link["url"]
    # Prefer combined video+audio
    for link in links:
        if link.get("has_video") and link.get("has_audio"):
            return link["url"]
    # Prefer mp4
    for link in links:
        if link.get("stream_type") == "mp4":
            return link["url"]
    return links[0]["url"]
