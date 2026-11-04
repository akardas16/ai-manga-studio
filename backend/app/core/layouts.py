"""
Page-layout template library + selection logic.

A page = a layout template (ordered panel slots) + one image per panel + a text layer.
Templates are grouped by panel count so the auto-selector can match a story's N panels.
Slots are either {"shape":"rect", x,y,w,h} or {"shape":"poly", points:[[x,y],...]}.
Coordinates are on the CANVAS below (a 2:3 page).
"""
from typing import Optional, List, Dict

CANVAS = {"w": 1200, "h": 1800}

TEMPLATES: List[Dict] = [
    {"id": "two-stack", "name": "Stacked", "panels": 2, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 1164, "h": 873},
        {"i": 1, "shape": "rect", "x": 18, "y": 909, "w": 1164, "h": 873}]},
    {"id": "two-vert", "name": "Vertical", "panels": 2, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 573, "h": 1764},
        {"i": 1, "shape": "rect", "x": 609, "y": 18, "w": 573, "h": 1764}]},
    {"id": "two-diagonal", "name": "Diagonal", "panels": 2, "slots": [
        {"i": 0, "shape": "poly", "points": [[18, 18], [1182, 18], [1182, 520], [18, 1150]]},
        {"i": 1, "shape": "poly", "points": [[18, 1210], [1182, 580], [1182, 1782], [18, 1782]]}]},
    {"id": "two-burst", "name": "Action Burst", "panels": 2, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 1164, "h": 1180, "fx": "burst"},
        {"i": 1, "shape": "rect", "x": 18, "y": 1216, "w": 1164, "h": 566}]},
    {"id": "three-stack", "name": "Stacked", "panels": 3, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 1164, "h": 564},
        {"i": 1, "shape": "rect", "x": 18, "y": 600, "w": 1164, "h": 564},
        {"i": 2, "shape": "rect", "x": 18, "y": 1182, "w": 1164, "h": 600}]},
    {"id": "three-big-top", "name": "Big Top + 2", "panels": 3, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 1164, "h": 1050},
        {"i": 1, "shape": "rect", "x": 18, "y": 1086, "w": 573, "h": 696},
        {"i": 2, "shape": "rect", "x": 609, "y": 1086, "w": 573, "h": 696}]},
    {"id": "three-left-tall", "name": "Left Tall + 2", "panels": 3, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 573, "h": 1764},
        {"i": 1, "shape": "rect", "x": 609, "y": 18, "w": 573, "h": 873},
        {"i": 2, "shape": "rect", "x": 609, "y": 909, "w": 573, "h": 873}]},
    {"id": "three-diagonal", "name": "Diagonal", "panels": 3, "slots": [
        {"i": 0, "shape": "poly", "points": [[18, 18], [1182, 18], [1182, 470], [18, 640]]},
        {"i": 1, "shape": "poly", "points": [[18, 700], [1182, 530], [1182, 1130], [18, 1300]]},
        {"i": 2, "shape": "poly", "points": [[18, 1360], [1182, 1190], [1182, 1782], [18, 1782]]}]},
    {"id": "grid-4", "name": "Even Grid", "panels": 4, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 573, "h": 873},
        {"i": 1, "shape": "rect", "x": 609, "y": 18, "w": 573, "h": 873},
        {"i": 2, "shape": "rect", "x": 18, "y": 909, "w": 573, "h": 873},
        {"i": 3, "shape": "rect", "x": 609, "y": 909, "w": 573, "h": 873}]},
    {"id": "hero-left-4", "name": "Hero Left", "panels": 4, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 560, "h": 1764},
        {"i": 1, "shape": "rect", "x": 596, "y": 18, "w": 586, "h": 760},
        {"i": 2, "shape": "rect", "x": 596, "y": 796, "w": 586, "h": 484},
        {"i": 3, "shape": "rect", "x": 596, "y": 1298, "w": 586, "h": 484}]},
    {"id": "action-4", "name": "Action Burst", "panels": 4, "slots": [
        {"i": 0, "shape": "rect", "x": 18, "y": 18, "w": 1164, "h": 520, "fx": "burst"},
        {"i": 1, "shape": "rect", "x": 18, "y": 556, "w": 1164, "h": 620},
        {"i": 2, "shape": "rect", "x": 18, "y": 1194, "w": 573, "h": 588},
        {"i": 3, "shape": "rect", "x": 609, "y": 1194, "w": 573, "h": 588}]},
]

_BY_ID = {t["id"]: t for t in TEMPLATES}


def canvas_for(aspect_ratio: str) -> Dict:
    """Page canvas for a chosen page shape (e.g. '2:3', '9:16', '1:1').
    Width stays fixed; height follows the ratio. Falls back to the base 2:3 canvas."""
    width = CANVAS["w"]
    try:
        w, h = aspect_ratio.split(":")
        return {"w": width, "h": int(round(width * float(h) / float(w)))}
    except Exception:
        return dict(CANVAS)


def scale_template(template: Dict, target_canvas: Dict) -> Dict:
    """Scale a template's slot Y coordinates/heights to a target canvas height.
    Templates are authored on the base CANVAS (2:3); width is unchanged."""
    import copy
    fy = target_canvas["h"] / CANVAS["h"]
    if abs(fy - 1.0) < 1e-6:
        return template
    t = copy.deepcopy(template)
    for s in t["slots"]:
        if s["shape"] == "rect":
            s["y"] = int(round(s["y"] * fy))
            s["h"] = int(round(s["h"] * fy))
        else:
            s["points"] = [[x, int(round(y * fy))] for x, y in s["points"]]
    return t


def get_template(template_id: str) -> Optional[Dict]:
    return _BY_ID.get(template_id)


def templates_for(panel_count: int) -> List[Dict]:
    return [t for t in TEMPLATES if t["panels"] == panel_count]


def select_layout(panel_count: int, page_layout: Optional[Dict]) -> Optional[Dict]:
    """
    Resolve the template to use.
    - manual mode with a valid template_id -> that template
    - auto mode (or anything else) -> first template whose panel count matches N
    Falls back to the closest-by-panel-count template if no exact match exists.
    """
    page_layout = page_layout or {}
    if page_layout.get("mode") == "manual" and page_layout.get("template_id"):
        t = get_template(page_layout["template_id"])
        if t:
            return t
    matches = templates_for(panel_count)
    if matches:
        return matches[0]
    # fallback: nearest available panel count
    if TEMPLATES:
        return min(TEMPLATES, key=lambda t: abs(t["panels"] - panel_count))
    return None
