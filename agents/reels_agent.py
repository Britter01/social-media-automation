"""Reels agent — assembles short vertical-video Reels from carousel slides.

Takes a carousel post whose ``.slides`` list is already populated with
Supabase image URLs, downloads each frame, composites it onto a blurred
9:16 background, assembles a ~20-second slideshow with 0.3 s crossfade
transitions, optionally mixes in a curated local MP3 track from
``assets/music/``, and uploads the finished MP4 to Supabase Storage.

Returns a public HTTPS Supabase URL — ready to hand to the publisher for
Instagram Reels (Graph API ``media_type=REELS``) and Facebook Reels
(``video_reels`` endpoint).

Runtime requirements
--------------------
* moviepy >= 1.0.3  (pure Python; ships with ffmpeg bindings)
* ffmpeg binary on PATH  (add ``[phases.setup] nixPkgs = ["ffmpeg"]`` to
  nixpacks.toml — already done in this repo)
* Pillow, httpx — already in requirements.txt
"""

from __future__ import annotations

import logging
import os
import pathlib
import random
import shutil
import subprocess
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

# Curated local music tracks — see assets/music/README.md for how to add tracks.
_MUSIC_DIR = pathlib.Path(__file__).parent.parent / "assets" / "music"


class ReelsAgent:
    """Generates MP4 Reels from a carousel post's slide images."""

    def __init__(self) -> None:
        pass

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
        out.close()  # close before moviepy opens the same path via ffmpeg
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
        """Mix background music into the silent video using ffmpeg directly.

        Bypasses moviepy's Python audio layer (which uses audio_loop and
        produces clicks/static at loop boundaries). ffmpeg's -stream_loop -1
        loops the music natively with no artefacts, and -shortest trims to the
        video duration so the output is exactly the right length.
        """
        ffmpeg = self._ffmpeg_exe()

        out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", prefix="reel_audio_")
        out.close()

        cmd = [
            ffmpeg,
            "-y",
            "-i",
            video_path,
            "-stream_loop",
            "-1",  # loop music indefinitely until video ends
            "-i",
            music_path,
            "-filter_complex",
            f"[1:a]volume={MUSIC_VOLUME}[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",  # copy video stream — no re-encode
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",  # trim to whichever input ends first (the video)
            out.name,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio mix failed: {result.stderr.decode(errors='replace')[-400:]}"
            )
        return out.name

    @staticmethod
    def _ffmpeg_exe() -> str:
        """Return the ffmpeg binary (system PATH or imageio-ffmpeg bundle)."""
        import shutil

        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise RuntimeError("ffmpeg not found on PATH or via imageio-ffmpeg") from exc

    # ── Music ──────────────────────────────────────────────────────────────────

    def _fetch_music(self, pillar: str) -> str | None:
        """Pick a random local MP3 for *pillar* from ``assets/music/``.

        Looks in ``assets/music/{pillar_slug}/`` first, then falls back to
        ``assets/music/default/``. Returns a temp copy of the chosen file so
        the caller's cleanup loop can safely unlink it without affecting the
        source asset. Returns None (silent reel) if no tracks are found.
        """
        pillar_slug = pillar.lower().replace(" ", "_")

        candidates: list[pathlib.Path] = []
        for folder_name in (pillar_slug, "default"):
            folder = _MUSIC_DIR / folder_name
            if folder.is_dir():
                found = sorted(f for f in folder.iterdir() if f.suffix.lower() == ".mp3")
                if found:
                    candidates = found
                    break

        if not candidates:
            logger.info(
                "ReelsAgent: no local music tracks for pillar %r — reel will be silent", pillar
            )
            return None

        chosen = random.choice(candidates)
        logger.info("ReelsAgent: selected music track %s for pillar %r", chosen.name, pillar)

        # Copy to a temp file so the caller's finally-block can unlink it safely
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="reel_music_")
        tmp.close()
        shutil.copy2(str(chosen), tmp.name)
        return tmp.name

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
