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
import re
from typing import Optional
from browser_extractor import intercept_browser, MEDIA_URL_PATTERNS


# Regex to identify media segments/chunks (usually low-value)
SEGMENT_PATTERNS = re.compile(
    r"[-_](seg|chunk|part|frag|fragment|track|init|video\d|audio\d)[-_]|\d+\.ts|\d+\.m4v",
    re.IGNORECASE,
)


async def extract_links(url: str, use_browser: bool = True, timeout: int = 25) -> dict:
    browser_results = []
    ytdlp_result = None
    errors = []

    # ── Strategy 0: Check if URL is already a direct media link ────────────────
    is_direct = bool(MEDIA_URL_PATTERNS.search(url.split('?')[0]))

    # ── Strategy 1: Headless browser interception ──────────────────────────────
    if use_browser:
        try:
            if not is_direct:
                browser_results = await intercept_browser(url, timeout_ms=timeout * 1000)
            else:
                # Add the direct link to browser_results manually
                browser_results = [{
                    "url": url,
                    "stream_type": _guess_type_from_url(url),
                    "source": "direct_input"
                }]
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
    # Filter browser results to remove likely ads (very small files that aren't HLS)
    filtered_browser_links = []
    AD_KEYWORDS = ("ads", "vast", "click", "pop", "preroll", "midroll", "postroll", "sponsored")
    
    for link in browser_results:
        # If it's a known ad domain or has ad keywords, skip it entirely
        if any(k in link["url"].lower() for k in AD_KEYWORDS):
            continue

        # 1DM Logic: Filter out likely segments/chunks unless it's the ONLY thing found
        is_segment = bool(SEGMENT_PATTERNS.search(link["url"]))
        if is_segment and link.get("stream_type") != "hls":
            continue

        # If it's HLS, we keep it (playlists are small)
        if link.get("stream_type") == "hls":
            filtered_browser_links.append(link)
            continue
            
        # If it has a known content length and it's tiny (< 1.5MB), it's likely an ad or segment
        length = link.get("content_length")
        if length and length < 1_500_000:
            continue
            
        filtered_browser_links.append(link)

    all_links = list(filtered_browser_links)

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

    # Sort: combined streams first, then by height, then by filesize
    unique_links.sort(
        key=lambda x: (
            bool(x.get("has_video") and x.get("has_audio")),
            x.get("height") or 0,
            x.get("filesize") or x.get("content_length") or 0,
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
    # Expanded Ad-Shield: Check URL AND Referer for ad patterns
    AD_KEYWORDS = (
        "ads", "vast", "crossdomain", "traffic", "click", "pop", "pre-roll", 
        "mid-roll", "post-roll", "creative", "affiliate", "tracking", "pixel"
    )
    AD_DOMAINS = ("contentabc.com", "exoclick.com", "doubleclick.net", "googlesyndication.com")
    
    clean_links = []
    for l in links:
        url_lower = l["url"].lower()
        referer_lower = (l.get("referer") or "").lower()
        
        # If the URL or Referer matches an ad pattern, skip it
        if any(k in url_lower or k in referer_lower for k in AD_KEYWORDS):
            continue
        if any(d in url_lower or d in referer_lower for d in AD_DOMAINS):
            continue
            
        clean_links.append(l)
    
    target_links = clean_links if clean_links else links

    # 1. 1DM Preference: Direct Site Media (High Quality)
    # If we find a direct link on the same domain or a media script, favor it!
    for link in target_links:
        u = link["url"].lower()
        # Prioritize site-specific media scripts like remote_control.php or get_file
        if "remote_control.php" in u or "get_file" in u:
            return link["url"]

    # 2. Prefer JS Sniffer HLS
    for link in target_links:
        if link.get("source", "").startswith("js_") and ".m3u8" in link["url"]:
             return link["url"]

    # 3. Prefer Master Manifests
    MASTER_MANIFEST_KEYWORDS = ("master", "playlist", "index", "manifest", "m3u8", "main")
    for link in target_links:
        if link.get("stream_type") == "hls":
            u = link["url"].lower()
            if any(k in u for k in MASTER_MANIFEST_KEYWORDS):
                if not SEGMENT_PATTERNS.search(u):
                    return link["url"]
            
    # 4. Prefer regular HLS
    for link in target_links:
        if link.get("stream_type") == "hls":
            return link["url"]
            
    # 5. Prefer JS Sniffer MP4/WebM (usually the result of a menu click)
    for link in target_links:
        if link.get("source", "").startswith("js_") and link.get("stream_type") in ("mp4", "webm"):
             return link["url"]

    # 6. Prefer combined video+audio
    for link in target_links:
        if link.get("has_video") and link.get("has_audio"):
            return link["url"]
            
    # 7. Prefer MP4
    for link in target_links:
        if link.get("stream_type") == "mp4":
            return link["url"]
            
    return target_links[0]["url"]


def _guess_type_from_url(url: str) -> str:
    path = url.split('?')[0].lower()
    if ".m3u8" in path: return "hls"
    if ".mpd" in path: return "dash"
    if ".mp4" in path: return "mp4"
    if ".webm" in path: return "webm"
    return "unknown"


async def extract_raw_ytdlp(url: str) -> dict:
    """Run yt-dlp on the URL. If it fails or yields no formats, fallback to Playwright."""
    loop = asyncio.get_event_loop()
    
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

    if ytdlp_info and ytdlp_info.get("formats"):
        return ytdlp_info

    # Otherwise, run browser interception (or handle direct link)
    try:
        is_direct = bool(MEDIA_URL_PATTERNS.search(url.split('?')[0]))
        if is_direct:
            browser_results = [{
                "url": url,
                "stream_type": _guess_type_from_url(url),
                "source": "direct_input"
            }]
        else:
            browser_results = await intercept_browser(url, timeout_ms=25000)
    except Exception as e:
        raise ValueError(f"Both yt-dlp and browser interception failed: {e}")

    # Filter results
    filtered_browser_links = []
    AD_KEYWORDS = ("ads", "vast", "click", "pop", "preroll", "midroll", "postroll", "sponsored")
    
    for link in browser_results:
        if any(k in link["url"].lower() for k in AD_KEYWORDS):
            continue

        # 1DM Logic: Filter out likely segments/chunks
        is_segment = bool(SEGMENT_PATTERNS.search(link["url"]))
        if is_segment and link.get("stream_type") != "hls":
            continue

        if link.get("stream_type") == "hls":
            filtered_browser_links.append(link)
            continue
        length = link.get("content_length")
        if length and length < 1_500_000:
            continue
        filtered_browser_links.append(link)

    if not filtered_browser_links:
        if ytdlp_info:
            return ytdlp_info
        if browser_results:
             filtered_browser_links = [browser_results[0]]
        else:
            raise ValueError("Could not extract any media links from this page.")

    # Sort candidates
    filtered_browser_links.sort(
        key=lambda x: (
            x.get("stream_type") == "hls",
            any(k in x["url"].lower() for k in ("master", "playlist", "index")),
            x.get("content_length") or 0
        ),
        reverse=True
    )

    fake_info = {
        "id": "browser_extract",
        "title": "Extracted Video",
        "extractor": "Playwright",
        "webpage_url": url,
        "formats": []
    }

    for i, link in enumerate(filtered_browser_links):
        fmt = {
            "format_id": f"browser_{i}",
            "url": link["url"],
            "ext": (link.get("content_type") or "").split("/")[-1] or "mp4",
            "vcodec": "avc1" if link.get("stream_type") in ("mp4", "hls", "dash", "video") else "none",
            "acodec": "mp4a" if link.get("stream_type") in ("mp4", "hls", "dash", "audio", "video") else "none",
        }
        
        if link.get("stream_type") == "hls":
            fmt["protocol"] = "m3u8_native"
            fmt["ext"] = "mp4"
            fmt["format_note"] = "HLS Stream"
        elif link.get("stream_type") == "audio":
            fmt["vcodec"] = "none"
            fmt["ext"] = "m4a"
            fmt["format_note"] = "Audio Stream"
            
        fmt["width"] = 1280
        fmt["height"] = 720
        if link.get("content_length"):
            fmt["filesize"] = link["content_length"]
            
        fake_info["formats"].append(fmt)

    return fake_info
