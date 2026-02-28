# Direct Link Grabber API

A fast REST API that extracts **direct download links** from video URLs on YouTube, Twitter/X, Instagram, TikTok, Reddit, Facebook, Vimeo, and [1000+ other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) — powered by **yt-dlp** and **FastAPI**.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/`      | API info |
| `GET`  | `/health`| Health check |
| `GET`  | `/grab?url=<VIDEO_URL>` | Grab links (query param) |
| `POST` | `/grab`  | Grab links (JSON body) |
| `GET`  | `/docs`  | Interactive Swagger UI |

### Example — GET request
```
GET /grab?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

### Example — POST request
```json
POST /grab
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "quality": "best"
}
```

### Example Response
```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "title": "Video Title",
  "duration": 212.0,
  "thumbnail": "https://...",
  "extractor": "youtube",
  "best_video": "https://rr3---sn-....googlevideo.com/...",
  "best_audio": "https://rr3---sn-....googlevideo.com/...",
  "formats": [
    {
      "format_id": "137",
      "ext": "mp4",
      "url": "https://...",
      "height": 1080,
      "has_video": true,
      "has_audio": false,
      ...
    }
  ]
}
```

---

## Local Development

### Using Docker Compose
```bash
docker compose up --build
```
API available at `http://localhost:8000`

### Without Docker
```bash
pip install -r requirements.txt
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

1. Go to [app.koyeb.com](https://app.koyeb.com) → **Create Service**
2. Select **GitHub** as the source and choose your repository
3. Under **Builder**, select **Dockerfile** (Koyeb auto-detects it)
4. Set the **Port** to `8000` (or leave it — Koyeb injects `PORT` env var automatically)
5. Click **Deploy**

### Step 3 — Done!
Koyeb gives you a public URL like:
```
https://your-service-name.koyeb.app/
```

Use `/docs` for the interactive Swagger UI.

---

## Supported Sites
Any site supported by yt-dlp — [full list here](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).
Includes: YouTube, Twitter/X, Instagram, TikTok, Reddit, Facebook, Vimeo, Dailymotion, Twitch, and 1000+ more.

---

## Notes
- Direct links for YouTube are **time-limited** (expire after a few hours) — that's a YouTube restriction.
- For best results with age-restricted content, add cookies via yt-dlp's `cookiefile` option.
- ffmpeg is bundled in the Docker image for merging video+audio streams.
