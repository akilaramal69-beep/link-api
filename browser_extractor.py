import asyncio
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Request

# Media content types to intercept
MEDIA_CONTENT_TYPES = (
    "video/",
    "audio/",
    "application/x-mpegurl",      # HLS
    "application/vnd.apple.mpegurl",  # HLS alt
    "application/dash+xml",        # DASH
    "application/octet-stream",    # Raw binary (often video)
    "application/x-www-form-urlencoded",
)

# URL patterns that indicate video/audio streams
MEDIA_URL_PATTERNS = re.compile(
    r"\.(mp4|m3u8|m4v|m4a|mpd|ts|webm|mkv|flv|avi|mov|aac|mp3|ogg|opus)(\?|$)",
    re.IGNORECASE,
)

# Patterns to ignore (ads, trackers, tiny thumbnails, etc.)
IGNORE_PATTERNS = re.compile(
    r"(doubleclick|googlesyndication|adservice|analytics|googletagmanager"
    r"|thumbnail|poster|preview|sprite|storyboard|\.jpg|\.jpeg|\.png|\.gif|\.webp"
    r"|/ads/|/ad/|tracking|beacon|pixel)",
    re.IGNORECASE,
)

# Minimum bytes to consider a response as a real media file
MIN_CONTENT_LENGTH = 50_000  # 50 KB


async def intercept_browser(url: str, timeout_ms: int = 20000) -> list[dict]:
    """
    Launch a headless Chromium browser, navigate to the URL, and intercept
    all media/stream network requests — like IDM does.
    Returns a list of detected media links with metadata.
    """
    found: dict[str, dict] = {}  # keyed by URL to deduplicate

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--mute-audio",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        page = await context.new_page()

        async def on_request(request: Request):
            req_url = request.url
            if IGNORE_PATTERNS.search(req_url):
                return

            # Match by URL pattern
            if MEDIA_URL_PATTERNS.search(req_url):
                _add_media_entry(found, req_url, source="url_pattern", request=request)

        async def on_response(response):
            try:
                resp_url = response.url
                if IGNORE_PATTERNS.search(resp_url):
                    return

                content_type = response.headers.get("content-type", "")
                content_length = int(response.headers.get("content-length", "0") or "0")

                is_media_type = any(mt in content_type.lower() for mt in MEDIA_CONTENT_TYPES)
                is_media_url = bool(MEDIA_URL_PATTERNS.search(resp_url))

                if is_media_type or is_media_url:
                    # Filter out tiny responses (icons, thumbnails)
                    if content_length > 0 and content_length < MIN_CONTENT_LENGTH:
                        return
                    _add_media_entry(
                        found,
                        resp_url,
                        source="response_header",
                        content_type=content_type,
                        content_length=content_length,
                    )
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            # Give the page extra time to start media streams
            await asyncio.sleep(5)

            # Try clicking play buttons to trigger video loading
            for selector in [
                "button[aria-label*='play' i]",
                "button[class*='play' i]",
                ".play-button",
                ".ytp-play-button",
                "video",
                "[data-testid*='play' i]",
            ]:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        await el.click(timeout=2000)
                        await asyncio.sleep(3)
                        break
                except Exception:
                    pass

            # Also extract <video> / <source> / <audio> src attributes from DOM
            dom_links = await page.evaluate("""() => {
                const urls = new Set();
                document.querySelectorAll('video, audio, source').forEach(el => {
                    if (el.src) urls.add(el.src);
                    if (el.currentSrc) urls.add(el.currentSrc);
                });
                document.querySelectorAll('source').forEach(el => {
                    if (el.src) urls.add(el.src);
                });
                return Array.from(urls).filter(u => u.startsWith('http'));
            }""")

            for link in dom_links:
                if not IGNORE_PATTERNS.search(link):
                    _add_media_entry(found, link, source="dom")

        except Exception as e:
            if not found:
                raise RuntimeError(f"Browser navigation failed: {e}")
        finally:
            await browser.close()

    return list(found.values())


def _add_media_entry(
    found: dict,
    url: str,
    source: str = "unknown",
    request=None,
    content_type: str = "",
    content_length: int = 0,
):
    if url in found:
        return

    parsed = urlparse(url)
    path = parsed.path.lower()

    # Detect stream type
    if ".m3u8" in path:
        stream_type = "hls"
    elif ".mpd" in path:
        stream_type = "dash"
    elif ".mp4" in path or ".m4v" in path:
        stream_type = "mp4"
    elif ".webm" in path:
        stream_type = "webm"
    elif ".mp3" in path or ".aac" in path or ".m4a" in path or ".ogg" in path or ".opus" in path:
        stream_type = "audio"
    elif ".ts" in path:
        stream_type = "ts_segment"
    elif "video" in content_type:
        stream_type = "video"
    elif "audio" in content_type:
        stream_type = "audio"
    else:
        stream_type = "unknown"

    found[url] = {
        "url": url,
        "stream_type": stream_type,
        "content_type": content_type or None,
        "content_length": content_length or None,
        "source": source,
        "referer": request.headers.get("referer") if request else None,
    }
