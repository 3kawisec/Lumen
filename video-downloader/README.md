# Lumen — Video Downloader

A clean, self-hosted web app that downloads a video from a link in the best
quality available. Beautiful front-end, tiny Python backend powered by
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp) (1000+ supported sites).

> **Why a backend?** A plain web page can't download videos from YouTube /
> TikTok / Instagram — those sites don't hand their files to the browser.
> The real work has to happen on a server. Lumen runs that server **on your own
> machine**, so nothing is sent anywhere else.

![quality](https://img.shields.io/badge/quality-best%20available-7c5cff) ![local](https://img.shields.io/badge/runs-100%25%20local-13d9c4)

---

## Quick start

### The easy way

- **Windows:** double-click **`start.bat`**
- **macOS / Linux:** run **`./start.sh`** in a terminal
  (first time: `chmod +x start.sh`)

Then open **http://127.0.0.1:8000** in your browser.

### The manual way

```bash
# 1. (optional but recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. run it
python backend/app.py
```

Open **http://127.0.0.1:8000**, paste a link, pick a quality, hit download.

---

## Install ffmpeg (strongly recommended)

`yt-dlp` can fetch 4K/1080p video and audio as *separate* streams. **ffmpeg**
merges them into one file and powers MP3 extraction. Without it you're limited
to lower combined qualities.

| OS | Command |
|----|---------|
| **macOS** | `brew install ffmpeg` |
| **Windows** | `winget install ffmpeg`  (or `choco install ffmpeg`) |
| **Ubuntu/Debian** | `sudo apt install ffmpeg` |

Lumen auto-detects ffmpeg — no config needed.

---

## Sites that need a login (Instagram, X, private/age-gated videos)

Platforms like **Instagram** and **X/Twitter** won't serve a video to anyone who
isn't signed in. Lumen can reuse the login from a browser you're already signed
into — no passwords, it just reads that browser's cookies.

Set `LUMEN_BROWSER_COOKIES` to your browser's name before starting Lumen:

```bash
# macOS / Linux
LUMEN_BROWSER_COOKIES=safari ./start.sh        # or: chrome, firefox, brave, edge

# Windows (PowerShell)
$env:LUMEN_BROWSER_COOKIES="chrome"; .\start.bat
```

Then be **logged into that browser** on the site you're downloading from, and
fetch the link again. (On macOS, reading Safari/Chrome cookies may prompt for
your keychain password the first time — that's the OS, not Lumen.)

> Tip: public YouTube, TikTok, Vimeo, etc. generally need no login at all.

---

## About watermarks

For sites like TikTok, `yt-dlp` already grabs the **clean source** (no burned-in
watermark) automatically — Lumen just downloads the best version the platform
serves. Some platforms *bake* a watermark into the actual pixels; that can't be
removed without cropping/re-encoding, which lowers quality, so Lumen doesn't do
that — it keeps your download sharp instead.

---

## Features

- 🎯 **Best quality by default** — auto-selects the highest-res video + audio
- 🎛️ **Pick your resolution** — 2160p/1440p/1080p/720p… chips built from what's available
- 🎵 **Audio-only (MP3 320k)** — one tap
- ⚡ **Live download progress** right in the page
- 🖥️ **100% local** — your links never leave your computer
- 🎨 Thoughtful, responsive dark UI

---

## Project layout

```
video-downloader/
├── backend/
│   └── app.py            # FastAPI + yt-dlp (info + download endpoints)
├── frontend/
│   └── index.html        # the entire UI (self-contained)
├── requirements.txt
├── start.sh / start.bat  # one-click launchers
└── README.md
```

## Change the port

```bash
PORT=9000 python backend/app.py      # macOS/Linux
set PORT=9000 && python backend\app.py   # Windows
```

## Updating yt-dlp

Sites change constantly. If a download stops working, update the engine:

```bash
pip install -U yt-dlp
```

---

## Responsible use

Lumen is a personal tool. **You** are responsible for complying with the terms
of service of each site and with copyright law. Download your own content, or
content you have permission or the right to save — and credit creators.
