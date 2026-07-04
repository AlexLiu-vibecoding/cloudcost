#!/usr/bin/env python3
"""Convert asciinema .cast recordings to animated GIFs.

Usage: python demo/cast2gif.py <recording.cast> [output.gif]

Requires: Pillow (pip install Pillow)
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# Terminal color theme (Dracula-like dark theme)
BG_COLOR = (40, 42, 54)        # #282a36
FG_COLOR = (248, 248, 242)     # #f8f8f2
PROMPT_COLOR = (80, 250, 123)  # #50fa7b (green)
CURSOR_COLOR = (248, 248, 242)
BAR_COLOR = (68, 71, 90)       # title bar

FONT_SIZE = 16
LINE_HEIGHT = 20
PADDING_X = 12
PADDING_TOP = 36  # room for title bar
COLUMNS = 90
ROWS = 24
FPS = 10  # frames per second for animation


def load_cast(cast_path: str) -> tuple[dict, list]:
    """Load an asciinema .cast file."""
    with open(cast_path) as f:
        header = json.loads(f.readline())
        events = []
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return header, events


def render_frame(
    lines: list[str], width: int, height: int, font: ImageFont.FreeTypeFont
) -> Image.Image:
    """Render a single frame of the terminal."""
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rectangle([(0, 0), (width, 28)], fill=BAR_COLOR)
    # Title bar buttons
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([(8 + i * 20, 8), (20 + i * 20, 20)], fill=color)
    draw.text((70, 5), "CloudCost Demo — Terminal", fill=(200, 200, 200), font=font)

    # Terminal content
    y = PADDING_TOP
    for line in lines[-ROWS:]:
        if line.startswith("$ "):
            draw.text((PADDING_X, y), "$ ", fill=PROMPT_COLOR, font=font)
            draw.text((PADDING_X + font.getlength("$ "), y), line[2:], fill=FG_COLOR, font=font)
        else:
            draw.text((PADDING_X, y), line, fill=FG_COLOR, font=font)
        y += LINE_HEIGHT

    return img


def cast_to_gif(cast_path: str, output_path: str = "demo.gif") -> None:
    """Convert asciicast to animated GIF."""
    header, events = load_cast(cast_path)

    # Determine dimensions
    width = header.get("width", COLUMNS)
    height = header.get("height", ROWS)
    img_width = width * (FONT_SIZE // 2) + PADDING_X * 2
    img_height = height * LINE_HEIGHT + PADDING_TOP + 4

    # Try to load a monospace font
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            font = ImageFont.truetype(fp, FONT_SIZE)
            break

    if font is None:
        print("Warning: No monospace font found, using default")
        font = ImageFont.load_default()

    # Build terminal state
    screen = [""] * height
    frames = []
    last_time = 0.0

    for event in events:
        time, event_type, data = event

        if event_type == "o":
            # Output text
            for char in data:
                if char == "\n":
                    # scroll up: insert empty line at bottom
                    screen = screen[1:] + [""]
                elif char == "\r":
                    # carriage return — clear current line
                    if screen:
                        screen[-1] = ""
                else:
                    if screen:
                        screen[-1] += char
                    else:
                        screen.append(char)

        # Render frame if enough time passed
        if time - last_time >= 1.0 / FPS:
            # Convert screen to displayable lines (split on \n within lines)
            display_lines = []
            for s in screen:
                display_lines.extend(s.split("\n"))

            frame = render_frame(display_lines, img_width, img_height, font)
            frames.append(frame)
            last_time = time

    if not frames:
        print("No frames generated")
        return

    # Add a final pause frame
    for _ in range(FPS):  # 1 second pause at end
        frames.append(frames[-1].copy())

    # Save as GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),  # ms per frame
        loop=0,
        optimize=True,
    )
    print(f"GIF saved: {output_path} ({len(frames)} frames, {img_width}x{img_height})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cast2gif.py <recording.cast> [output.gif]")
        sys.exit(1)

    cast_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "demo/cloudcost-demo.gif"
    cast_to_gif(cast_path, output_path)
