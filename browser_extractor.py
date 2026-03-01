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

# Patterns to ignore (ads, trackers, image thumbnails, etc.)
# Extremely aggressive ad-network filtering for video ads and redirects.
IGNORE_PATTERNS = re.compile(
    r"(doubleclick|googlesyndication|adservice|analytics|googletagmanager"
    r"|exoclick|trafficjunky|chaturbate|jerkmate|bongacams|stripchat|popads"
    r"|bidgear|adsco|outbrain|taboola|mgid|vast|vpaid|ima3|preroll|midroll"
    r"|postroll|advertisement|branded|sponsor|tracking|pixel|beacon"
    r"|popunder|clickunder|onclick|adsterra|propellerads|adespresso|yandex"
    r"|\.jpg|\.jpeg|\.png|\.gif|\.webp|\.svg|\.ico|\.css|\.js|\.woff|\.ttf"
    r"|/ads/|/ad/|/pixel)",
    re.IGNORECASE,
)

# Minimum bytes to consider a response as a real media file
MIN_CONTENT_LENGTH = 50_000  # 50 KB


# JS Sniffer Script to be injected into every page/iframe (1DM-style)
SNIFFER_JS = """
(function() {
    const logMedia = (url, source) => {
        if (!url || typeof url !== 'string' || url.startsWith('blob:') || url.startsWith('data:')) return;
        if (window.pythonSniff) {
            window.pythonSniff(url, source);
        }
    };

    // 1. Hook into HTMLMediaElement prototype to catch .src assignments
    const originalSrcDescriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
        set: function(val) {
            logMedia(val, 'media_proto_src');
            return originalSrcDescriptor.set.apply(this, arguments);
        },
        get: function() {
            return originalSrcDescriptor.get.apply(this, arguments);
        }
    });

    // 2. Monitor events on all video/audio tags
    const monitorElement = (el) => {
        if (el._sniffed) return;
        el._sniffed = true;
        ['loadstart', 'play', 'playing', 'loadedmetadata'].forEach(ev => {
            el.addEventListener(ev, () => {
                logMedia(el.src || el.currentSrc, 'media_event_' + ev);
            }, { passive: true });
        });
    };

    document.querySelectorAll('video, audio').forEach(monitorElement);

    // 3. Watch for NEW media elements via MutationObserver
    const observer = new MutationObserver((mutations) => {
        mutations.forEach(m => {
            m.addedNodes.forEach(node => {
                if (node.nodeName === 'VIDEO' || node.nodeName === 'AUDIO') monitorElement(node);
                if (node.querySelectorAll) node.querySelectorAll('video, audio').forEach(monitorElement);
            });
        });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });

    // 4. Periodically check currentSrc (fallback)
    setInterval(() => {
        document.querySelectorAll('video, audio').forEach(el => {
            logMedia(el.currentSrc || el.src, 'media_poll');
        });
    }, 2000);
})();
"""

async def intercept_browser(url: str, timeout_ms: int = 25000) -> list[dict]:
    """
    Launch a headless Chromium browser, navigate to the URL, and intercept
    all media/stream network requests — like 1DM does.
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
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

        # Inject 1DM-style sniffer script into every frame
        await context.add_init_script(SNIFFER_JS)

        page = await context.new_page()

        # ── 1DM Hardening: Block Popups & Dialogs ─────────────────────────────
        # Close any popup windows immediately (click-unders)
        page.on("popup", lambda p: asyncio.create_task(p.close()))
        # Automatically dismiss alerts/prompts (ad-scams)
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        # Binding to receive JS-discovered links
        async def python_sniff(source_info, media_url, sniffer_source):
            if media_url and media_url.startswith('http'):
                # Still check against ignore patterns to be safe
                if not IGNORE_PATTERNS.search(media_url) or MEDIA_URL_PATTERNS.search(media_url):
                    _add_media_entry(found, media_url, source=f"js_{sniffer_source}")

        await page.expose_binding("pythonSniff", python_sniff)

        async def on_request(request: Request):
            req_url = request.url
            if IGNORE_PATTERNS.search(req_url) and not MEDIA_URL_PATTERNS.search(req_url):
                return
            if MEDIA_URL_PATTERNS.search(req_url):
                _add_media_entry(found, req_url, source="url_pattern", request=request)

        async def on_response(response):
            try:
                resp_url = response.url
                is_media_url = bool(MEDIA_URL_PATTERNS.search(resp_url))
                
                if not is_media_url and IGNORE_PATTERNS.search(resp_url):
                    return

                content_type = response.headers.get("content-type", "")
                content_length = int(response.headers.get("content-length", "0") or "0")
                
                if "image/" in content_type or "text/" in content_type:
                    return

                is_media_type = any(mt in content_type.lower() for mt in MEDIA_CONTENT_TYPES)

                if is_media_type or is_media_url:
                    if content_length > 0 and content_length < MIN_CONTENT_LENGTH and not is_media_url:
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
            await asyncio.sleep(8) # Wait extra for 1DM-style sniffing to fire

            # Aggressive discovery: loop through frames and click/sniff
            frames = page.frames
            for frame in frames:
                # 1. Evaluate DOM links (fallback)
                try:
                    dom_links = await frame.evaluate("""() => {
                        const urls = new Set();
                        document.querySelectorAll('video, audio, source').forEach(el => {
                            if (el.src) urls.add(el.src);
                            if (el.currentSrc) urls.add(el.currentSrc);
                        });
                        return Array.from(urls).filter(u => u.startsWith('http'));
                    }""")
                    for link in dom_links:
                        if not IGNORE_PATTERNS.search(link) or MEDIA_URL_PATTERNS.search(link):
                            _add_media_entry(found, link, source="dom_scan")
                except Exception:
                    pass

                # 2. Trigger play buttons
                for selector in [
                    "button[aria-label*='play' i]",
                    "button[class*='play' i]",
                    ".play-button",
                    "video",
                    "[data-testid*='play' i]",
                ]:
                    try:
                        el = await frame.query_selector(selector)
                        if el:
                            await el.click(timeout=1500)
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        pass

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
