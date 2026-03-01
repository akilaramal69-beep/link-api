# Direct Link Grabber API (V5)

An upgraded **1DM-style** REST API that extracts **direct download links** from video URLs on **any website** — powered by **Playwright** (Advanced JS Sniffing) + **yt-dlp** enrichment.

---

## 🤖 Universal Telegram Bot Compatibility
This API is a drop-in backend for Telegram bots (like `telelinkworking`). It fabricates high-accuracy yt-dlp responses for sites that yt-dlp doesn't natively support.

Set `YT_API_URL` in your bot's `config.env`:
```
YT_API_URL=https://your-service.koyeb.app
```

---

## ⚡ V5 Features: 1DM-Style Sniffing & Accuracy
Version 5 introduces the "1DM Sniffer" logic for unmatched extraction reliability:

1.  **Script Injection (1DM Logic):** Injects a JS sniffer into every page/iframe to hook `HTMLMediaElement.prototype` and catch media URLs the moment they are assigned by Javascript.
2.  **Dropdown Menu Discovery:** Automatically identifies hidden "Download" menus and triggers quality selection (480p, 720p, MP4) to reveal direct media links.
3.  **Accurate Fetching:** Strictly prioritizes **site-direct media** (e.g., `remote_control.php`, `get_file/`) and **Master Manifests** (`.m3u8`) over low-quality fragments.
4.  **Hardened Ad-Shield:** Automatically kills popups, click-under ads, and silences JS alert-scams.
5.  **Strategy 0 (Direct Link):** Instant recognition of `.m3u8` or `.mp4` URLs to save 100% of RAM.

---

## 🚀 How to Call the API

### 1. Using `curl` (Terminal)
**To get the best direct link instantly:**
```bash
curl "https://your-service.koyeb.app/grab?url=https://example.com/video/123"
```

**To get full yt-dlp compatible JSON:**
```bash
curl -X POST "https://your-service.koyeb.app/extract" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://example.com/video/123"}'
```

### 2. Using Python
```python
import requests

api_url = "https://your-service.koyeb.app/grab"
video_url = "https://www.tabootube.xxx/video/younger-brothers-porn-fantasy-hd"

response = requests.get(api_url, params={"url": video_url})
data = response.json()

print(f"Direct Link: {data['best_link']}")
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/grab?url=<URL>` | **Recommended.** Returns clean JSON with `best_link`. |
| `POST` | `/extract` | **For Bots.** Returns full yt-dlp JSON dump with Playwright fallback. |
| `GET`  | `/health` | API Status check. |

---

## Local Development

### Docker (Recommended)
```bash
docker compose up --build
```

### Manual Install
```bash
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --port 8000
```

---

## Deploy on Koyeb (1-Click)

1. Push this folder to a private **GitHub** repository.
2. On **Koyeb**, create a new service and select the repository.
3. Set the builder to **Dockerfile** and port to **8000**.
4. Click **Deploy**. Done! ✅
