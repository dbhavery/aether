"""
Generate photorealistic product scene images for Anima showcase.
Uses FLUX.1-dev via diffusers to create realistic usage scenarios.

Scenes:
1. Person at home desk, late night, small avatar window glowing on second monitor
2. Person holding phone showing avatar face, blurred commute background
3. Close-up phone screen with avatar in video mode, warm ambient
4. Desk setup from above - monitor, keyboard, coffee, avatar window visible
5. Person at laptop in coffee shop, small avatar widget on screen
6. Split view: code editor left, phone-sized avatar window right on desktop
7. Person relaxed on couch, phone showing avatar face
8. Meeting room, phone on table showing text mode with notes

Usage:
  cd C:\\Users\\dbhav\\Projects\\aether
  python scripts/generate_showcase_scenes.py

Output: aether/.superpowers/brainstorm/cortex-showcase/scenes/
"""

import torch
from diffusers import FluxPipeline
from pathlib import Path
import gc

# ── Config ────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent.parent / ".superpowers" / "brainstorm" / "cortex-showcase" / "scenes"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ID = "black-forest-labs/FLUX.1-dev"
DEVICE = "cuda"
DTYPE = torch.float16  # fp16 for 24GB VRAM
STEPS = 28
GUIDANCE = 3.5
WIDTH = 1024
HEIGHT = 1024

# ── Prompts ───────────────────────────────────────────────────────
# Each prompt describes a photorealistic scene of someone using
# an AI assistant with a photorealistic female avatar on their screen.

SCENES = [
    {
        "name": "01_desk_night",
        "prompt": (
            "Photorealistic image of a person sitting at a modern home office desk late at night, "
            "dark room illuminated only by two monitors. On the right monitor, a small phone-sized "
            "window shows a photorealistic blonde woman's face - an AI assistant avatar. The main "
            "monitor shows a code editor with dark theme. The person is typing. Warm desk lamp "
            "provides amber accent light. City view through window behind. Shot from over the shoulder. "
            "Cinematic lighting, shallow depth of field, 35mm photography, editorial quality."
        ),
    },
    {
        "name": "02_phone_commute",
        "prompt": (
            "Photorealistic close-up of a person's hands holding a smartphone on a train or subway. "
            "The phone screen shows a photorealistic blonde woman's face taking up the full screen - "
            "an AI assistant in video mode. The background is blurred subway interior with warm "
            "tungsten lighting. Morning commute atmosphere. The phone has a dark app interface with "
            "minimal UI - just the avatar face and small status indicator. Shot at eye level, "
            "shallow depth of field, 50mm lens, natural light, editorial photography."
        ),
    },
    {
        "name": "03_phone_closeup",
        "prompt": (
            "Photorealistic extreme close-up of a modern smartphone screen showing a photorealistic "
            "blonde woman with green eyes looking directly at the viewer - an AI assistant avatar "
            "in video call mode. The phone has a dark UI with small 'Text | Video' mode tabs at top. "
            "The background behind the phone is a blurred modern apartment with warm ambient lighting. "
            "The screen glows softly, casting warm light. Macro photography style, very shallow "
            "depth of field, premium product photography, 85mm lens."
        ),
    },
    {
        "name": "04_desk_overhead",
        "prompt": (
            "Photorealistic overhead shot of a minimalist desk setup. Dark wooden desk surface with "
            "a mechanical keyboard, wireless mouse, coffee cup, notebook, and a single ultrawide monitor. "
            "On the right side of the monitor screen, a small phone-sized window shows a blonde woman's "
            "face - an AI assistant. The rest of the screen shows a design tool. Warm desk lamp light "
            "from upper left. Clean, organized workspace. Flat lay style photography, "
            "soft directional lighting, editorial quality, 24mm wide angle."
        ),
    },
    {
        "name": "05_coffee_shop",
        "prompt": (
            "Photorealistic image of a person working on a laptop at a coffee shop table. The laptop "
            "screen shows a code editor, and in the bottom right corner is a small window with a "
            "photorealistic blonde woman's face - an AI assistant widget. A coffee cup sits nearby. "
            "Warm natural light from a large window. Other patrons blurred in background. The person "
            "is focused on their work while the AI assistant is present but unobtrusive. "
            "Documentary style, 35mm, shallow depth of field, warm color grading."
        ),
    },
    {
        "name": "06_split_desktop",
        "prompt": (
            "Photorealistic screenshot of a desktop computer screen showing a split workspace. "
            "Left side: VS Code dark theme with Python code visible. Right side: a phone-sized "
            "floating window showing a photorealistic blonde woman with green eyes - an AI assistant "
            "avatar in video mode, with a small chat panel below her face. Dark UI, minimal chrome. "
            "The window has macOS-style traffic light dots. Monitor bezels visible at edges. "
            "Slightly angled view of the screen, as if photographed from the user's perspective. "
            "Clean, sharp, professional monitor photography."
        ),
    },
    {
        "name": "07_couch_relaxed",
        "prompt": (
            "Photorealistic image of a person relaxed on a dark modern couch, holding their phone "
            "at a comfortable angle. The phone screen shows a photorealistic blonde woman smiling - "
            "an AI assistant in video mode. Evening atmosphere, warm living room lighting, soft "
            "shadows. The person looks comfortable and casual. A table lamp provides warm amber light. "
            "The scene feels intimate and natural - like talking to a friend on video call. "
            "Lifestyle photography, 50mm, warm tones, shallow depth of field."
        ),
    },
    {
        "name": "08_meeting_phone",
        "prompt": (
            "Photorealistic image of a conference room table during a meeting. A smartphone lies "
            "face-up on the table showing a dark chat interface with text messages - an AI assistant "
            "in text mode providing meeting notes. Other people's hands and laptops visible around "
            "the table, slightly blurred. The phone screen is in focus showing the conversation. "
            "Modern office with glass walls. Cool overhead fluorescent mixed with warm daylight. "
            "Documentary photography style, 35mm, selective focus on the phone."
        ),
    },
]


def generate():
    print(f"Loading FLUX.1-dev from {MODEL_ID}...")
    print(f"Output directory: {OUTPUT_DIR}")

    pipe = FluxPipeline.from_pretrained(
        MODEL_ID,
        torch_dtype=DTYPE,
    )
    # Enable memory optimizations for 24GB VRAM
    pipe.enable_model_cpu_offload()

    for scene in SCENES:
        name = scene["name"]
        prompt = scene["prompt"]
        output_path = OUTPUT_DIR / f"{name}.png"

        if output_path.exists():
            print(f"  Skipping {name} (already exists)")
            continue

        print(f"\n  Generating: {name}")
        print(f"  Prompt: {prompt[:80]}...")

        image = pipe(
            prompt=prompt,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE,
            width=WIDTH,
            height=HEIGHT,
            generator=torch.Generator(DEVICE).manual_seed(42),
        ).images[0]

        image.save(output_path)
        print(f"  Saved: {output_path}")

        # Free memory between generations
        gc.collect()
        torch.cuda.empty_cache()

    print(f"\nDone. {len(SCENES)} scenes generated in {OUTPUT_DIR}")


if __name__ == "__main__":
    generate()
