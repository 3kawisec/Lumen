"""
Lumen — a self-hosted video downloader.

A tiny FastAPI backend that powers the front-end in ../frontend.
It uses yt-dlp (the open-source engine that supports 1000+ sites) to:
  * read a video's metadata + available qualities   -> POST /api/info
  * download the chosen quality and hand you the file -> POST /api/download

Everything runs on YOUR machine. You are responsible for respecting each
site's Terms of Service and the rights of the people who made the video.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

try:
    from yt_dlp import YoutubeDL
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "yt-dlp is not installed. Run:  pip install -r requirements.txt"
    ) from exc


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #

FRONTEND_DIR = (Path(__file__).resolve().parent.parent / "frontend").resolve()
HAS_FFMPEG = shutil.which("ffmpeg") is not None

# Some sites (Instagram, X, age-gated/private videos) require you to be logged
# in. Set LUMEN_BROWSER_COOKIES to your browser name to let yt-dlp reuse your
# existing login, e.g.:  LUMEN_BROWSER_COOKIES=safari  (or chrome / firefox / edge / brave)
BROWSER_COOKIES = os.environ.get("LUMEN_BROWSER_COOKIES", "").strip().lower() or None

app = FastAPI(title="Lumen Video Downloader", version="1.1.0")

# Allow the page to call the API even if someone serves the frontend elsewhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _json_errors(_request: Request, exc: Exception) -> JSONResponse:
    """Guarantee every error reaches the browser as JSON (never plain text),
    so the UI can always show a readable message."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": _friendly_error(exc)})


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: Optional[str] = None  # None / "best" -> best available
    audio_only: bool = False


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name or "video")[:120]


def _human_size(num: Optional[float]) -> Optional[str]:
    if not num:
        return None
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return None


def _base_opts() -> dict[str, Any]:
    # A normal desktop UA avoids some sites refusing automated clients.
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    }
    if BROWSER_COOKIES:
        # yt-dlp reads your logged-in session straight from the browser.
        opts["cookiesfrombrowser"] = (BROWSER_COOKIES,)
    return opts


def _simplify_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn yt-dlp's raw format list into a clean, de-duplicated menu."""
    formats = info.get("formats") or []
    seen: dict[str, dict[str, Any]] = {}

    for f in formats:
        if f.get("vcodec") == "none":  # skip audio-only here; handled separately
            continue
        height = f.get("height")
        if not height:
            continue
        ext = f.get("ext") or "mp4"
        label = f"{height}p"
        fps = f.get("fps")
        if fps and fps >= 50:
            label += f"{int(round(fps))}"
        key = f"{height}-{ext}"

        has_audio = f.get("acodec") not in (None, "none")
        entry = {
            "format_id": f.get("format_id"),
            "label": label,
            "height": height,
            "ext": ext,
            "fps": fps,
            "filesize": _human_size(f.get("filesize") or f.get("filesize_approx")),
            "needs_merge": not has_audio,
            "tbr": f.get("tbr") or 0,
        }
        # Prefer mp4 and the higher-bitrate variant for a given resolution+ext.
        prev = seen.get(key)
        if prev is None or (entry["tbr"] or 0) > (prev["tbr"] or 0):
            seen[key] = entry

    # Sort: highest resolution first, mp4 preferred on ties.
    ordered = sorted(
        seen.values(),
        key=lambda e: (e["height"], e["ext"] == "mp4", e["tbr"] or 0),
        reverse=True,
    )
    return ordered


def _extract_info(url: str) -> dict[str, Any]:
    opts = _base_opts()
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # yt-dlp raises many subclasses
        raise HTTPException(status_code=400, detail=_friendly_error(exc)) from exc
    if not info:
        raise HTTPException(
            status_code=400,
            detail="No video could be read from that link (it may need a login).",
        )
    return info


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    needs_login = any(
        k in low for k in ("login required", "log in", "sign in", "cookies",
                           "private", "authenticate", "restricted")
    )
    if needs_login:
        hint = ("This video needs you to be logged in. Enable browser cookies: "
                "set LUMEN_BROWSER_COOKIES to your browser (e.g. safari or chrome) "
                "and restart Lumen. See the README.")
        return hint
    if "rate" in low and "limit" in low:
        return ("The site is rate-limiting requests right now. Wait a minute and "
                "try again — logging in (browser cookies) also helps.")
    if "unsupported url" in low or "no suitable" in low:
        return "That link isn't supported, or it isn't a direct video page."
    if "not available" in low or "removed" in low or "404" in low:
        return "The video seems unavailable or was removed."
    if "unable to download webpage" in low or "failed to resolve" in low:
        return "Couldn't reach that site. Check the link and your connection."
    # Last resort: surface a trimmed real reason instead of a generic line.
    clean = msg.replace("ERROR:", "").strip()
    return (clean[:180] + "…") if len(clean) > 180 else (clean or
            "Couldn't process this link. Double-check it and try again.")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ffmpeg": HAS_FFMPEG}


@app.post("/api/info")
def api_info(req: InfoRequest) -> dict[str, Any]:
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please paste a link first.")

    info = _extract_info(url)

    # A playlist/channel page returns entries; grab the first real video.
    if info.get("_type") == "playlist" and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise HTTPException(status_code=400, detail="No video found at that link.")
        info = entries[0]

    duration = info.get("duration")
    pretty_duration = None
    if duration:
        m, s = divmod(int(duration), 60)
        h, m = divmod(m, 60)
        pretty_duration = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    return {
        "title": info.get("title") or "Untitled video",
        "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key"),
        "thumbnail": info.get("thumbnail"),
        "duration": pretty_duration,
        "source": info.get("extractor_key"),
        "webpage_url": info.get("webpage_url") or url,
        "formats": _simplify_formats(info),
        "ffmpeg": HAS_FFMPEG,
    }


@app.post("/api/download")
def api_download(req: DownloadRequest):
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please paste a link first.")

    workdir = Path(tempfile.mkdtemp(prefix="lumen_"))
    cleanup = BackgroundTask(shutil.rmtree, workdir, ignore_errors=True)

    opts = _base_opts()
    opts["outtmpl"] = str(workdir / "%(title).120s.%(ext)s")

    if req.audio_only:
        opts["format"] = "bestaudio/best"
        if HAS_FFMPEG:
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                 "preferredquality": "320"}
            ]
    else:
        fid = (req.format_id or "").strip()
        if not fid or fid == "best":
            # Highest-quality video + audio, merged into one file.
            opts["format"] = "bv*+ba/b" if HAS_FFMPEG else "b[ext=mp4]/b"
        else:
            # A specific resolution. If it's video-only, add the best audio.
            opts["format"] = f"{fid}+ba/{fid}/b" if HAS_FFMPEG else f"{fid}/b"
        if HAS_FFMPEG:
            opts["merge_output_format"] = "mp4"

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("_type") == "playlist" and info.get("entries"):
                info = next((e for e in info["entries"] if e), info)
            produced = Path(ydl.prepare_filename(info))
    except Exception as exc:
        cleanup()
        raise HTTPException(status_code=400, detail=_friendly_error(exc)) from exc

    # Postprocessing (merge / mp3) can change the final extension.
    final = produced
    if not final.exists():
        candidates = sorted(workdir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        candidates = [p for p in candidates if p.is_file()]
        if not candidates:
            cleanup()
            raise HTTPException(status_code=500, detail="Download finished but no file was produced.")
        final = candidates[0]

    title = _sanitize_filename(info.get("title") or "video")
    download_name = f"{title}{final.suffix}"

    return FileResponse(
        path=str(final),
        filename=download_name,
        media_type="application/octet-stream",
        background=cleanup,
    )


# --------------------------------------------------------------------------- #
# Frontend (served from the same origin so the browser never blocks it)
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Frontend not found</h1>", status_code=500)
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


# Serve any other static assets if you add them later (css/js/img).
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print("\n  Lumen is running!  Open  ->  http://127.0.0.1:%d\n" % port)
    if not HAS_FFMPEG:
        print("  Note: ffmpeg not found. Highest-res merging & mp3 will be limited.")
        print("  Install ffmpeg for best quality (see README).\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
