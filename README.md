# Direct Link Grabber API

An IDM-style REST API that extracts **direct download links** from video URLs on **any website** — powered by **Playwright** (headless browser interception) + **yt-dlp** fallback.

Works on YouTube, Twitter/X, Instagram, TikTok, Reddit, Facebook, Vimeo, Dailymotion, Twitch, and virtually **any site that streams video in a browser** (even unsupported sites like `milfnut.com`!).

---

## 🤖 Universal Telegram Bot Compatibility
This API includes a dedicated `/extract` endpoint specifically designed to act as a **drop-in backend replacing yt-dlp** for bots like `telelinkworking`. 

Set `YT_API_URL` in your bot's `config.env` to your Koyeb deployment URL:
```
YT_API_URL=https://your-service.koyeb.app
```

**What makes this special?**
If your bot sends an unsupported URL (like `milfnut.com`), or if `yt-dlp` is temporarily blocked by YouTube, the API seamlessly spins up its IDM-style headless browser. It traverses all `iframes`, intercepts the raw `.m3u8` or `.mp4` video files, and **fabricates a perfect fake yt-dlp response**. Your bot will magically process it as if `yt-dlp` natively supported the website!

---

## How It Works

```
API Request (Any URL)
  │
  ├── 1. Try yt-dlp extraction (Fastest, best metadata)
  │
  └── 2. IF yt-dlp fails (Unsupported site / Blocked):
         ├── Launch Headless Chromium browser
         ├── Traverse all iframes & click Play buttons
         ├── Intercept raw IDM network requests (.mp4, .m3u8, .ts, etc)
         ├── Ignore ads/trackers
         └── Format links into a unified JSON structure
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | API info |
| `GET`  | `/health` | Health check |
| `GET`  | `/grab?url=<URL>` | Extract links (custom IDM format) |
| `POST` | `/grab` | Extract links (JSON body, custom IDM format) |
| `POST` | `/extract` | **yt-dlp JSON dump** (Provides seamless Playwright fallback) |

### POST `/extract` (For Bots)
```json
POST /extract
{
  "url": "https://milfnut.com/..."
}
```
*Returns the exact dictionary output of `yt-dlp`. If yt-dlp fails, it returns a fake yt-dlp dictionary populated with Playwright-intercepted links.* 
*(Note: Never returns HTTP 400 errors for extraction failures to prevent bots from falling back to downloading HTML web pages. It instead returns a 200 OK with `{"formats": []}`).*

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
├── extractor.py         # Orchestrator (browser → yt-dlp fallback logic)
├── browser_extractor.py # Playwright IDM interception engine
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

> ⚠️ The Docker image is ~800MB due to Chromium. This is normal and fully supported on Koyeb.
