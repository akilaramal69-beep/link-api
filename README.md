# Direct Link Grabber API

An IDM-style REST API that extracts **direct download links** from video URLs on **any website** — powered by **Playwright** (headless browser interception) + **yt-dlp** fallback.

Works on YouTube, Twitter/X, Instagram, TikTok, Reddit, Facebook, Vimeo, Dailymotion, Twitch, and virtually **any site that streams video in a browser**.

---

## 🤖 Telegram Bot Compatibility (telelinkworking)
This API includes a dedicated `/extract` endpoint specifically designed to act as a backend for the `telelinkworking` Telegram bot. 
Set `YT_API_URL` in your bot's `config.env` to your Koyeb deployment URL:
```
YT_API_URL=https://your-service.koyeb.app
```
The bot will securely offload YouTube (and other) extraction to this API to bypass IP bans and local throttling.

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
| `GET`  | `/grab?url=<URL>` | Extract links (custom IDM format) |
| `POST` | `/grab` | Extract links (JSON body, custom IDM format) |
| `POST` | `/extract` | **Raw yt-dlp dump** (Exact drop-in for bots) |
| `GET`  | `/docs` | Swagger UI |

### POST `/extract` (For Bots)
```json
POST /extract
{
  "url": "https://youtube.com/watch?v=..."
}
```
*Returns the exact dictionary output of `yt-dlp`'s `extract_info` function.*

### GET `/grab` Example (IDM Style)
```
GET /grab?url=https://example.com/video/123
GET /grab?url=https://youtu.be/dQw4w9WgXcQ&use_browser=false
```

### POST `/grab` Example (IDM Style)
```json
POST /grab
{
  "url": "https://any-streaming-site.com/video/123",
  "use_browser": true,
  "timeout": 25
}
```
*Returns a clean, unified JSON with `best_link`, stream types, and browser/ytdlp sources.*

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
