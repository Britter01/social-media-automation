"""Video agent — short videos via the HeyGen API with a cloned voice.

Submits a video generation job to HeyGen v2, then polls v1 status until
the video is ready (or fails / times out). The avatar and the cloned
voice are referenced by the IDs configured in the environment.

HeyGen flow:
  1. POST /v2/video/generate  -> { video_id }
  2. GET  /v1/video_status.get?video_id=...  (poll until status == 'completed')
  3. read video_url from the completed status payload
"""

from __future__ import annotations

import logging
import time

import httpx

from core.config import Config, config
from core.models import Post, PostStatus

logger = logging.getLogger(__name__)

_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
_STATUS_URL = "https://api.heygen.com/v1/video_status.get"


class VideoGenerationError(RuntimeError):
    """Raised when HeyGen reports a failed job or polling times out."""


def _script_from_post(post: Post) -> str:
    """Build the spoken script. Keep it tight for short-form video."""
    # The caption is written for reading; for a talking-head clip we lead
    # with the hook, then the body, capped to keep the clip short.
    body = post.caption or post.topic or post.title
    script = f"{post.title}. {body}" if post.title else body
    return script.strip()[:1500]


class VideoAgent:
    """Creates a talking-head video for a post via HeyGen."""

    def __init__(
        self,
        cfg: Config = config,
        poll_interval: float = 10.0,
        timeout: float = 600.0,
    ) -> None:
        cfg.require("heygen_api_key", "heygen_voice_id", "heygen_avatar_id")
        self._cfg = cfg
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._headers = {
            "X-Api-Key": cfg.heygen_api_key,
            "Content-Type": "application/json",
        }

    def generate(self, post: Post) -> Post:
        """Generate a video and set ``post.video_url`` in place."""
        video_id = self._submit(post)
        logger.info("Submitted HeyGen job %s for post %s", video_id, post.id)
        video_url = self._wait_for_completion(video_id)
        post.video_url = video_url
        post.mark(PostStatus.MEDIA_READY)
        logger.info("Video ready for post %s -> %s", post.id, video_url)
        return post

    # --- HeyGen API ------------------------------------------------------

    def _submit(self, post: Post) -> str:
        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": self._cfg.heygen_avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": _script_from_post(post),
                        "voice_id": self._cfg.heygen_voice_id,
                    },
                }
            ],
            "dimension": _dimension_for(post.platform),
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(_GENERATE_URL, headers=self._headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            logger.exception("HeyGen submit failed for post %s", post.id)
            raise

        video_id = (data.get("data") or {}).get("video_id")
        if not video_id:
            raise VideoGenerationError(f"HeyGen returned no video_id: {data}")
        return video_id

    def _wait_for_completion(self, video_id: str) -> str:
        deadline = time.monotonic() + self._timeout
        with httpx.Client(timeout=60.0) as client:
            while time.monotonic() < deadline:
                try:
                    resp = client.get(
                        _STATUS_URL,
                        headers=self._headers,
                        params={"video_id": video_id},
                    )
                    resp.raise_for_status()
                    data = (resp.json() or {}).get("data") or {}
                except httpx.HTTPError:
                    logger.warning(
                        "HeyGen status poll errored for %s; retrying",
                        video_id,
                        exc_info=True,
                    )
                    time.sleep(self._poll_interval)
                    continue

                status = data.get("status")
                if status == "completed":
                    url = data.get("video_url")
                    if not url:
                        raise VideoGenerationError(f"HeyGen completed without a video_url: {data}")
                    return url
                if status in {"failed", "error"}:
                    raise VideoGenerationError(f"HeyGen job {video_id} failed: {data.get('error')}")

                logger.debug("HeyGen job %s status=%s; waiting", video_id, status)
                time.sleep(self._poll_interval)

        raise VideoGenerationError(
            f"HeyGen job {video_id} did not complete within {self._timeout}s"
        )


def _dimension_for(platform: str) -> dict:
    """Vertical for short-form platforms, landscape for YouTube."""
    if platform in {"tiktok", "instagram"}:
        return {"width": 1080, "height": 1920}
    return {"width": 1920, "height": 1080}
