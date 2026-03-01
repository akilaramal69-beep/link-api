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
        
    # Strictly prefer HLS > video+audio > mp4
    for link in links:
        if link.get("stream_type") == "hls":
            return link["url"]
            
    for link in links:
        if link.get("has_video") and link.get("has_audio"):
            return link["url"]
            
    for link in links:
        if link.get("stream_type") == "mp4":
            return link["url"]
            
    # As a last resort, pick anything that isn't 'unknown' or 'audio' if possible
    for link in links:
        if link.get("stream_type") not in ("unknown", "audio"):
            return link["url"]
            
    # Absolute last resort
    return links[0]["url"]


async def extract_raw_ytdlp(url: str) -> dict:
    """Run yt-dlp on the URL. If it fails or yields no formats, fallback to Playwright
    and format the results as a fake yt-dlp info dict so the bot understands it."""
    loop = asyncio.get_event_loop()
    
    # Optional shortcut for obvious non-yt-dlp sites
    is_known = any(d in url.lower() for d in [
        "youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com", 
        "tiktok.com", "reddit.com", "facebook.com", "vimeo.com"
    ])
    
    ytdlp_info = None
    if is_known:
        try:
            ytdlp_info = await loop.run_in_executor(None, _ytdlp_extract, url)
        except Exception:
            pass

    # If yt-dlp gave us good formats, just return it directly (bot drops-in perfectly)
    if ytdlp_info and ytdlp_info.get("formats"):
        return ytdlp_info

    # Otherwise (like milfnut.com), run our browser interception!
    try:
        browser_results = await intercept_browser(url, timeout_ms=25000)
    except Exception as e:
        raise ValueError(f"Both yt-dlp and browser interception failed: {e}")

    if not browser_results:
        if ytdlp_info:
            return ytdlp_info  # return the empty ytdlp dict
        raise ValueError("Could not extract any media links from this page.")

    # Fabricate a fake yt-dlp dictionary perfectly tailored for `telelinkworking` plugin
    fake_info = {
        "id": "browser_extract",
        "title": "Extracted Video",
        "extractor": "Playwright",
        "webpage_url": url,
        "formats": []
    }

    for i, link in enumerate(browser_results):
        fmt = {
            "format_id": f"browser_{i}",
            "url": link["url"],
            "ext": "mp4", # Bot generally prefers mp4 default
            "vcodec": "avc1" if link.get("stream_type") in ("mp4", "hls", "dash", "video") else "none",
            "acodec": "mp4a" if link.get("stream_type") in ("mp4", "hls", "dash", "audio", "video") else "none",
        }
        
        # Make HLS look like standard yt-dlp HLS formats
        if link.get("stream_type") == "hls":
            fmt["protocol"] = "m3u8_native"
            fmt["ext"] = "mp4"
            fmt["format_note"] = "HLS Stream"
        elif link.get("stream_type") == "audio":
            fmt["vcodec"] = "none"
            fmt["ext"] = "m4a"
            fmt["format_note"] = "Audio Stream"
            
        # Hardcode a resolution so the bot's format selector UI works (it expects things like 720p)
        fmt["width"] = 1280
        fmt["height"] = 720
        
        # Inject standard byte size if known
        if link.get("content_length"):
            fmt["filesize"] = link["content_length"]
            
        fake_info["formats"].append(fmt)

    return fake_info
