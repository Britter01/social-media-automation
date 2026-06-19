"""Reels agent — assembles short vertical-video Reels from carousel slides.

Takes a carousel post whose ``.slides`` list is already populated with
Supabase image URLs, downloads each frame, composites it onto a blurred
9:16 background, assembles a ~20-second slideshow with 0.3 s crossfade
transitions, optionally mixes in a royalty-free CC0 music track from the
Freesound API, and uploads the finished MP4 to Supabase Storage.

Returns a public HTTPS Supabase URL — ready to hand to the publisher for
Instagram Reels (Graph API ``media_type=REELS``) and Facebook Reels
(``video_reels`` endpoint).

Runtime requirements
--------------------
* moviepy >= 1.0.3  (pure Python; ships with ffmpeg bindings)
* ffmpeg binary on PATH  (add ``[phases.setup] nixPkgs = ["ffmpeg"]`` to
  nixpacks.toml — already done in this repo)
* Pillow, httpx — already in requirements.txt
* FREESOUND_API_KEY in Railway env vars for background music (optional —
  Reels are still produced silently if the key is absent or the search
  returns nothing)
"""

from __future__ import annotations

import logging
import os
import random
import tempfile

import httpx
from PIL import Image, ImageFilter

from core.config import config as _config
from core.models import Post

logger = logging.getLogger(__name__)

# ── Video constants ────────────────────────────────────────────────────────────

REEL_W = 1080
REEL_H = 1920
SLIDE_DURATION = 5.0  # seconds each slide is visible
CROSSFADE_DUR = 0.3  # seconds crossfade between slides
FPS = 24
MUSIC_VOLUME = 0.25  # 25% — keeps text slides as the focal point

# ── Freesound search terms per content pillar ──────────────────────────────────

_PILLAR_QUERIES: dict[str, str] = {
    "AI Guide": "ambient electronic technology",
    "Tech Lifestyle": "upbeat background electronic",
    "Productivity": "focus lo-fi concentration",
    "Fitness Tech": "energetic motivational beat",
    "Review": "calm cinematic ambient",
}
_FREESOUND_SEARCH = "https://freesound.org/apiv2/search/text/"


class ReelsAgent:
    """Generates MP4 Reels from a carousel post's slide images."""

    def __init__(self) -> None:
        self._freesound_key = getattr(_config, "freesound_api_key", None)

    # ── Public entry point ─────────────────────────────────────────────────────

    def generate_video_url(self, carousel_post: Post) -> str | None:
        """Build a Reel from *carousel_post* slides and return its Supabase URL.

        Returns ``None`` on any failure so callers can degrade gracefully
        rather than marking the parent carousel post as failed.
        """
        if not carousel_post.slides:
            logger.warning("ReelsAgent: post %s has no slides — skipping", carousel_post.id)
            return None

        temp_files: list[str] = []
        try:
            slide_paths = self._download_slides(carousel_post.slides)
            temp_files.extend(slide_paths)

            frame_paths = [self._make_9x16_frame(p) for p in slide_paths]
            temp_files.extend(frame_paths)

            video_path = self._build_slideshow(frame_paths)
            temp_files.append(video_path)

            music_path = self._fetch_music(carousel_post.pillar)
            if music_path:
                temp_files.append(music_path)
                mixed_path = self._mix_audio(video_path, music_path, carousel_post.id)
                temp_files.append(mixed_path)
                video_path = mixed_path

            url = self._upload(video_path, carousel_post.id)
            logger.info("ReelsAgent: uploaded reel for post %s → %s", carousel_post.id, url)
            return url

        except Exception:
            logger.exception("ReelsAgent: failed for post %s", carousel_post.id)
            return None

        finally:
            for p in temp_files:
                try:
                    if p and os.path.exists(p):
                        os.unlink(p)
                except OSError:
                    pass

    # ── Frame preparation ──────────────────────────────────────────────────────

    def _download_slides(self, slides: list[dict]) -> list[str]:
        """Download slide image URLs to temp PNG files."""
        paths: list[str] = []
        with httpx.Client(timeout=30.0) as client:
            for i, slide in enumerate(slides):
                url = slide.get("image_url", "")
                if not url:
                    continue
                resp = client.get(url)
                resp.raise_for_status()
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".png", prefix=f"reel_dl_{i}_"
                )
                tmp.write(resp.content)
                tmp.close()
                paths.append(tmp.name)
        if not paths:
            raise RuntimeError("ReelsAgent: no slide images could be downloaded")
        return paths

    def _make_9x16_frame(self, slide_path: str) -> str:
        """Composite slide onto a 1080×1920 blurred background copy of itself."""
        img = Image.open(slide_path).convert("RGB")
        W, H = REEL_W, REEL_H

        # Background: scale image to fill 1080×1920, then blur + darken.
        bg_scale = max(W / img.width, H / img.height)
        bg = img.resize(
            (int(img.width * bg_scale), int(img.height * bg_scale)),
            Image.LANCZOS,
        )
        x_off = (bg.width - W) // 2
        y_off = (bg.height - H) // 2
        bg = bg.crop((x_off, y_off, x_off + W, y_off + H))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
        bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), alpha=0.45)

        # Foreground: scale to fit within the centre of the frame.
        pad = 60
        max_w = W - pad * 2  # 960 px
        fg_scale = max_w / img.width
        # Don't let height exceed 80% of frame height (keeps margins visible).
        if img.height * fg_scale > H * 0.80:
            fg_scale = (H * 0.80) / img.height
        fg = img.resize(
            (int(img.width * fg_scale), int(img.height * fg_scale)),
            Image.LANCZOS,
        )
        x = (W - fg.width) // 2
        y = (H - fg.height) // 2
        bg.paste(fg, (x, y))

        out = tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix="reel_frame_")
        bg.save(out.name)
        return out.name

    # ── Video assembly ─────────────────────────────────────────────────────────

    def _build_slideshow(self, frame_paths: list[str]) -> str:
        """Assemble frames into an mp4 with crossfade transitions (no audio)."""
        from moviepy.editor import ImageClip, concatenate_videoclips

        clips = []
        for i, path in enumerate(frame_paths):
            clip = ImageClip(path).set_duration(SLIDE_DURATION)
            if i > 0:
                clip = clip.crossfadein(CROSSFADE_DUR)
            clips.append(clip)

        video = concatenate_videoclips(clips, padding=-CROSSFADE_DUR, method="compose")

        out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", prefix="reel_silent_")
        video.write_videofile(
            out.name,
            fps=FPS,
            codec="libx264",
            audio=False,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "baseline", "-level", "3.0"],
            logger=None,
        )
        video.close()
        return out.name

    def _mix_audio(self, video_path: str, music_path: str, post_id: str) -> str:
        """Mix background music into the silent slideshow at reduced volume."""
        from moviepy.audio.fx.all import audio_loop
        from moviepy.editor import AudioFileClip, VideoFileClip

        video = VideoFileClip(video_path)
        duration = video.duration

        raw_audio = AudioFileClip(music_path)
        if raw_audio.duration < duration:
            music = audio_loop(raw_audio, duration=duration).volumex(MUSIC_VOLUME)
        else:
            music = raw_audio.subclip(0, duration).volumex(MUSIC_VOLUME)

        video_with_audio = video.set_audio(music)

        out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", prefix="reel_audio_")
        video_with_audio.write_videofile(
            out.name,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            ffmpeg_params=["-pix_fmt", "yuv420p", "-profile:v", "baseline", "-level", "3.0"],
            logger=None,
        )
        video.close()
        video_with_audio.close()
        return out.name

    # ── Music ──────────────────────────────────────────────────────────────────

    def _fetch_music(self, pillar: str) -> str | None:
        """Fetch a CC0 preview track from Freesound matching the content pillar.

        Returns a local path to the downloaded mp3, or None if unavailable.
        Failures are always swallowed so a missing key / API hiccup never
        blocks Reel production.
        """
        if not self._freesound_key:
            return None

        query = _PILLAR_QUERIES.get(pillar, "ambient background")
        try:
            resp = httpx.get(
                _FREESOUND_SEARCH,
                params={
                    "query": query,
                    "filter": 'duration:[15 TO 120] license:"Creative Commons 0"',
                    "fields": "id,name,previews,duration",
                    "page_size": 15,
                    "token": self._freesound_key,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                logger.info("ReelsAgent: Freesound returned 0 results for %r", query)
                return None

            track = random.choice(results[:10])
            preview_url = (track.get("previews") or {}).get("preview-hq-mp3")
            if not preview_url:
                return None

            mp3 = httpx.get(preview_url, timeout=30.0, follow_redirects=True)
            mp3.raise_for_status()

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="reel_music_")
            tmp.write(mp3.content)
            tmp.close()
            logger.info("ReelsAgent: downloaded music track %r", track.get("name"))
            return tmp.name

        except Exception:
            logger.warning("ReelsAgent: could not fetch music from Freesound", exc_info=True)
            return None

    # ── Upload ─────────────────────────────────────────────────────────────────

    def _upload(self, video_path: str, post_id: str) -> str:
        """Upload the finished MP4 to Supabase Storage and return its public URL."""
        from supabase import create_client

        sb = create_client(_config.supabase_url, _config.supabase_key)
        bucket = _config.supabase_bucket
        storage_path = f"reels/{post_id}.mp4"

        with open(video_path, "rb") as f:
            sb.storage.from_(bucket).upload(
                storage_path,
                f,
                file_options={"content-type": "video/mp4", "upsert": "true"},
            )

        return sb.storage.from_(bucket).get_public_url(storage_path)
