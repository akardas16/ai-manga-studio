"""
Manga page compositor.

Composes a finished page from three independent layers:
  1. a layout template (panel slots, rect or polygon)
  2. one clean image per panel (no baked-in text)
  3. a text layer (speech bubbles + narration boxes)

Because the layers are independent, changing layout or text costs ZERO
image-generation calls — only the compositing step re-runs.
"""
import io
import os
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Gemini-supported aspect ratios (value -> w/h) used to size each generated panel.
ASPECTS = {
    "1:1": 1.0, "2:3": 2 / 3, "3:2": 3 / 2, "3:4": 3 / 4, "4:3": 4 / 3,
    "4:5": 4 / 5, "5:4": 5 / 4, "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9,
}

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def bbox(slot: Dict):
    """(x, y, w, h) bounding box for a rect or poly slot."""
    if slot["shape"] == "rect":
        return slot["x"], slot["y"], slot["w"], slot["h"]
    xs = [p[0] for p in slot["points"]]
    ys = [p[1] for p in slot["points"]]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def slot_aspect(slot: Dict) -> str:
    """Nearest supported Gemini aspect ratio for a slot's bounding box."""
    _, _, w, h = bbox(slot)
    r = w / h
    return min(ASPECTS, key=lambda k: abs(ASPECTS[k] - r))


def _font(size: int):
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _cover(img: Image.Image, w: int, h: int, y_focus: float = 0.32) -> Image.Image:
    """Scale + crop to exactly fill w x h (CSS object-fit: cover).
    Horizontal crop is centered; vertical crop is biased toward the top
    (y_focus = fraction of the overflow removed from the top) so that
    heads/faces — usually in the upper portion of a panel — are preserved."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = int((nh - h) * y_focus)
    return img.crop((left, top, left + w, top + h))


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


def _busyness(edges: Image.Image, box):
    """Mean edge energy inside box (x0,y0,x1,y1) of a FIND_EDGES grayscale image.
    Low = empty/flat region (sky, wall, floor); high = detail (faces, subjects)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(edges.width, x1); y1 = min(edges.height, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return 1e9
    region = edges.crop((x0, y0, x1, y1))
    hist = region.histogram()
    total = sum(hist) or 1
    # weighted mean pixel value = average edge strength
    return sum(i * c for i, c in enumerate(hist)) / total


def choose_anchor(tile: Image.Image, bubble_w: int, bubble_h: int):
    """Pick the emptiest placement for a bubble of bubble_w x bubble_h within the panel tile.
    Returns (cx_frac, cy_frac) center, in slot-relative fractions. Prefers upper positions."""
    W, H = tile.size
    edges = tile.convert("L").filter(ImageFilter.FIND_EDGES)
    # candidate centers as fractions, with a reading-order penalty for lower rows
    candidates = [
        (0.30, 0.17, 1.00), (0.70, 0.17, 1.00), (0.50, 0.15, 1.00),
        (0.30, 0.50, 1.18), (0.70, 0.50, 1.18),
        (0.30, 0.84, 1.30), (0.70, 0.84, 1.30), (0.50, 0.85, 1.30),
    ]
    best, best_score = (0.5, 0.15), 1e18
    for fx, fy, penalty in candidates:
        cx, cy = fx * W, fy * H
        box = (cx - bubble_w / 2, cy - bubble_h / 2, cx + bubble_w / 2, cy + bubble_h / 2)
        score = _busyness(edges, box) * penalty
        if score < best_score:
            best_score, best = score, (fx, fy)
    return best


def classify_dialogue(d: str):
    """'Speaker: text' -> (is_narration, clean_text)."""
    if not d:
        return False, ""
    low = d.lower().strip()
    is_narr = low.startswith("(anlat") or low.startswith("anlat") or "narration" in low or low.startswith("(narr")
    text = d.split(":", 1)[1].strip() if ":" in d else d
    return is_narr, text


def compose(template: Dict, canvas: Dict, panel_images: Dict, texts: List[Dict],
            border: int = 6) -> bytes:
    """
    template: {"slots":[{i,shape,...}, ...]}
    canvas:   {"w":..,"h":..}
    panel_images: {slot_index: PIL.Image}
    texts: [{"panel":i, "type":"speech"|"narration", "text":..., "anchor":{"x","y"}}]
    Returns PNG bytes of the composed page.
    """
    W, H = canvas["w"], canvas["h"]
    page = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(page)
    tiles = {}  # slot index -> the exact cover tile shown (for text placement)

    # ---- Layers 1+2: panels into slots ----
    for slot in template["slots"]:
        i = slot["i"]
        x, y, w, h = bbox(slot)
        if slot["shape"] == "rect":
            if i in panel_images and panel_images[i] is not None:
                tile = _cover(panel_images[i], w, h)
                tiles[i] = tile
                page.paste(tile, (x, y))
            draw.rectangle([x, y, x + w, y + h], outline="black", width=border)
        else:  # polygon
            pts = slot["points"]
            if i in panel_images and panel_images[i] is not None:
                tile = _cover(panel_images[i], w, h)
                tiles[i] = tile
                mask = Image.new("L", (w, h), 0)
                ImageDraw.Draw(mask).polygon([(px - x, py - y) for px, py in pts], fill=255)
                page.paste(tile, (x, y), mask)
            draw.line([tuple(p) for p in pts] + [tuple(pts[0])], fill="black",
                      width=border, joint="curve")

    # ---- Layer 3: text (speech bubbles + narration boxes) ----
    slot_by_i = {s["i"]: s for s in template["slots"]}
    for t in texts:
        slot = slot_by_i.get(t["panel"])
        if not slot or not t.get("text"):
            continue
        sx, sy, sw, sh = bbox(slot)
        fs = max(17, min(40, int(sw * 0.039)))
        font = _font(fs)
        lines = _wrap(draw, t["text"], font, int(sw * 0.52))
        line_h = fs + 5
        tw = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        th = line_h * len(lines)
        pad = int(fs * 0.5)

        # content-aware placement: drop the bubble into the emptiest region of the panel
        bubble_w, bubble_h = tw + 2 * pad, th + 2 * pad
        tile = tiles.get(t["panel"])
        if tile is not None:
            fx, fy = choose_anchor(tile, bubble_w, bubble_h)
        else:
            fx = t.get("anchor", {}).get("x", 0.5)
            fy = t.get("anchor", {}).get("y", 0.14)
        ax = sx + int(fx * sw)
        ay = sy + int(fy * sh) - th // 2  # fy is the bubble CENTER; shift to top-left origin
        bx0, by0 = ax - tw // 2 - pad, ay - pad
        bx1, by1 = ax + tw // 2 + pad, ay + th + pad
        bx0 = max(sx + 8, bx0); by0 = max(sy + 8, by0)
        bx1 = min(sx + sw - 8, bx1); by1 = min(sy + sh - 8, by1)

        if t.get("type") == "narration":
            draw.rounded_rectangle([bx0, by0, bx1, by1], radius=6, fill="#FDF5E6",
                                   outline="black", width=3)
            tcol = "#222222"
        else:
            draw.rounded_rectangle([bx0, by0, bx1, by1], radius=22, fill="white",
                                   outline="black", width=3)
            tcol = "black"
        ty = by0 + pad
        cx = (bx0 + bx1) // 2
        for ln in lines:
            lw = draw.textlength(ln, font=font)
            draw.text((cx - lw // 2, ty), ln, font=font, fill=tcol)
            ty += line_h

    buf = io.BytesIO()
    page.save(buf, format="PNG")
    return buf.getvalue()
