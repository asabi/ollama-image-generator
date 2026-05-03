"""Style templates for image generation.

A 'style' is a short string id (e.g. 'cartoon') paired with a prompt prefix
that gets prepended to the user's prompt on every generate. Selecting a
style always shapes the output — separately, the gemma enhance step uses
the same style hint to richen the prompt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    id: str
    label: str
    prefix: str          # prepended to the user prompt on generate
    enhance_hint: str    # short instruction for gemma when enhancing


STYLES: list[Style] = [
    Style(
        id="realistic",
        label="Realistic photo",
        prefix="A photorealistic photograph, sharp focus, natural lighting, high detail. ",
        enhance_hint="a photorealistic photograph (camera, lens, lighting, mood)",
    ),
    Style(
        id="cartoon",
        label="Cartoon",
        prefix="Cartoon illustration, bold outlines, vibrant flat colors, expressive characters. ",
        enhance_hint="a Western-style cartoon illustration (characters, colors, scene)",
    ),
    Style(
        id="anime",
        label="Anime",
        prefix="Anime illustration, cel-shaded, detailed line art, expressive eyes, dynamic composition. ",
        enhance_hint="an anime / manga illustration (characters, expression, lighting, mood)",
    ),
    Style(
        id="oil_painting",
        label="Oil painting",
        prefix="Oil painting, visible brush strokes, rich texture, classical composition. ",
        enhance_hint="a classical oil painting (subject, lighting, mood, brushwork)",
    ),
    Style(
        id="watercolor",
        label="Watercolor",
        prefix="Watercolor painting, soft washes, paper texture, delicate edges. ",
        enhance_hint="a watercolor painting (subject, palette, atmosphere)",
    ),
    Style(
        id="3d_render",
        label="3D render",
        prefix="High-quality 3D render, octane render, soft global illumination, detailed materials. ",
        enhance_hint="a polished 3D render (subject, materials, lighting, camera)",
    ),
    Style(
        id="pixel_art",
        label="Pixel art",
        prefix="Pixel art, 16-bit aesthetic, crisp pixels, limited palette. ",
        enhance_hint="pixel art (subject, palette, scene)",
    ),
    Style(
        id="sketch",
        label="Pencil sketch",
        prefix="Detailed pencil sketch, graphite shading, paper grain, hand-drawn lines. ",
        enhance_hint="a detailed pencil sketch (subject, shading, composition)",
    ),
    Style(
        id="cinematic",
        label="Cinematic",
        prefix="Cinematic shot, dramatic lighting, shallow depth of field, color-graded, film still. ",
        enhance_hint="a cinematic film still (subject, framing, lighting, mood)",
    ),
]

STYLE_BY_ID: dict[str, Style] = {s.id: s for s in STYLES}


def build_full_prompt(style_id: str, user_prompt: str) -> str:
    """Build the final prompt string handed to ollama: '<style prefix><user prompt>'.

    Width/height/seed/negative-prompt are passed to ollama as CLI flags,
    not embedded in the prompt text.
    """
    style = STYLE_BY_ID.get(style_id)
    if style is None:
        raise ValueError(f"Unknown style id: {style_id!r}")
    return style.prefix.rstrip() + " " + user_prompt.strip()
