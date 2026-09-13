"""Image generation via the Google Gemini image model.

One place for the Google image call, because it has now broken twice in ways
that had to be fixed in three files at once:

* google-genai 2.x made ``models.generate_images`` Vertex-only, so it raises on
  a plain ``GOOGLE_API_KEY``;
* Google shut the ``imagen-*`` models down on 17 Aug 2026, so the model id
  itself 404s.

The replacement is ``generate_content`` with an IMAGE response modality, which
works on a normal API key. Keeping it here means the next model or API change
is a one-line edit rather than a hunt.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_image(
    *,
    api_key: str,
    model: str,
    prompt: str,
    aspect_ratio: str = "1:1",
) -> bytes:
    """Return raw image bytes for *prompt*.

    Raises RuntimeError with the API's own reason when no image comes back —
    usually a safety block, which a bare "no images" would hide.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    return generate_image_with_client(
        client=client, model=model, prompt=prompt, aspect_ratio=aspect_ratio, types=types
    )


def generate_image_with_client(
    *,
    client,
    model: str,
    prompt: str,
    aspect_ratio: str = "1:1",
    types=None,
) -> bytes:
    """Same as :func:`generate_image` but reuses an existing client."""
    if types is None:
        from google.genai import types  # noqa: PLC0415 — optional dependency at call time

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )

    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            data = getattr(blob, "data", None)
            if data:
                return data

    finish = None
    for candidate in getattr(response, "candidates", None) or []:
        finish = getattr(candidate, "finish_reason", None) or finish
    feedback = getattr(response, "prompt_feedback", None)
    raise RuntimeError(
        f"{model} returned no image (finish_reason={finish}, prompt_feedback={feedback})"
    )
