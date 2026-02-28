# Direct Link Grabber API

An IDM-style REST API that extracts **direct download links** from video URLs on **any website** — powered by **Playwright** (headless browser interception) + **yt-dlp** fallback.

Works on YouTube, Twitter/X, Instagram, TikTok, Reddit, Facebook, Vimeo, Dailymotion, Twitch, and virtually **any site that streams video in a browser**.

---

## How It Works

```
URL → Headless Chromium loads the page (like a real browser)
    → Intercepts all network requests (MP4, HLS .m3u8, DASH .mpd, WebM, audio...)
    → Tries to auto-click play buttons to trigger lazy-loaded streams
    → Reads <video>/<source> DOM elements
    → yt-dlp enriches results for known platforms (YouTube, Twitter, etc.)
    → Returns unified list of direct links + best pick
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | API info |
| `GET`  | `/health` | Health check |
| `GET`  | `/grab?url=<URL>` | Extract links (query param) |
| `POST` | `/grab` | Extract links (JSON body) |
| `GET`  | `/docs` | Swagger UI |

### GET Example
```
GET /grab?url=https://example.com/video/123
GET /grab?url=https://youtu.be/dQw4w9WgXcQ&use_browser=false
```

### POST Example
```json
POST /grab
{
  "url": "https://any-streaming-site.com/video/123",
  "use_browser": true,
  "timeout": 25
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `url` | required | Any video page URL |
| `use_browser` | `true` | Use Playwright interception |
| `timeout` | `25` | Timeout in seconds |

### Response
```json
{
  "url": "https://...",
  "title": "Video Title",
  "thumbnail": "https://...",
  "duration": 212.0,
  "best_link": "https://direct-stream-url...",
  "total": 5,
  "links": [
    {
      "url": "https://...",
      "stream_type": "hls",
      "source": "browser",
      "has_video": true,
      "has_audio": true
    },
    {
      "url": "https://...",
      "stream_type": "mp4",
      "height": 1080,
      "source": "ytdlp"
    }
  ]
}
```

---

## Project Structure

```
.
├── main.py              # FastAPI app
├── extractor.py         # Orchestrator (browser → yt-dlp fallback)
├── browser_extractor.py # Playwright interception engine
├── requirements.txt
├── Dockerfile
└── docker-compose.yml   # Local testing
```

---

## Local Development

### Docker Compose
```bash
docker compose up --build
```
API available at `http://localhost:8000`

### Without Docker
```bash
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
```

---

## Deploy on Koyeb

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/direct-link-grabber
git push -u origin main
```

### Step 2 — Create Koyeb Service

1. [app.koyeb.com](https://app.koyeb.com) → **Create Service**
2. Source: **GitHub** → select your repo
3. Builder: **Dockerfile** (auto-detected)
4. Port: **8000**
5. Click **Deploy** ✅

Koyeb provides a public URL like `https://your-service.koyeb.app/`

> ⚠️ The Docker image is ~800MB due to Chromium. This is normal and supported on Koyeb.

---

## Notes
- YouTube direct links **expire** after a few hours — YouTube's restriction, not an API limitation.
- For sites requiring login/cookies, yt-dlp's `cookiefile` option can be added.
- `stream_type` values: `hls`, `dash`, `mp4`, `webm`, `video`, `audio`, `video+audio`, `ts_segment`
