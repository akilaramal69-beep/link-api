from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from extractor import extract_links
import uvicorn

app = FastAPI(
    title="Direct Link Grabber API",
    description=(
        "Extract direct download links from ANY video URL — works like IDM. "
        "Uses headless browser interception (Playwright) for any site, "
        "with yt-dlp as fallback for known platforms."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LinkRequest(BaseModel):
    url: str
    use_browser: bool = True   # False = force yt-dlp only
    timeout: int = 25          # seconds


# ── Health / Root ─────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    """Root endpoint — also handles HEAD for Koyeb health probes."""
    return {
        "message": "Direct Link Grabber API v2 — IDM-style",
        "endpoints": {
            "GET /grab?url=<URL>": "Grab links from any video URL",
            "POST /grab": '{"url": "...", "use_browser": true, "timeout": 25}',
            "GET /docs": "Swagger UI",
        },
    }


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    """Health check — supports both GET and HEAD (Koyeb probe)."""
    return {"status": "ok"}


# ── Grab endpoints ────────────────────────────────────────────────────────────

@app.get("/grab")
async def grab_get(
    url: str = Query(..., description="Any video page URL"),
    use_browser: bool = Query(True, description="Use headless browser interception"),
    timeout: int = Query(25, description="Timeout in seconds"),
):
    """Extract direct media links from any video URL."""
    try:
        result = await extract_links(url, use_browser=use_browser, timeout=timeout)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/grab")
async def grab_post(request: LinkRequest):
    """Extract direct media links from any video URL (POST)."""
    try:
        result = await extract_links(
            request.url,
            use_browser=request.use_browser,
            timeout=request.timeout,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/extract")
async def extract_post(request: Request):
    """Raw yt-dlp extraction for drop-in compatibility with Telegram bots like telelinkworking."""
    try:
        data = await request.json()
        url = data.get("url")
        if not url:
            return {"error": "Missing 'url' in JSON body", "formats": []}
            
        from extractor import extract_raw_ytdlp
        result = await extract_raw_ytdlp(url)
        return result
    except Exception as e:
        # Return 200 with soft error so the bot doesn't trigger its raw HTML fallback
        return {"error": str(e), "formats": [], "title": "Extraction Failed"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
