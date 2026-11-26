"""Progress card: one picture instead of a wall of numbers.

  left   a ring with the share of signs learned (big number, then learned / total)
         and the last 14 days of answers against the daily goal (dashed line)
  right  one bar per sign category, labelled by a real sign of that category

The picture carries no words (the built-in font has no Cyrillic); the caption explains it.
Colours follow the card theme the learner chose (light / dark).
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from utils import find_sign_image

W, H = 1280, 720
CATEGORY_SIGN = {
    "fareskilt": "100_1", "vikeplikt": "202_0", "forbudsskilt": "302_0", "pabudsskilt": "402_1",
    "opplysningsskilt": "502_0", "serviceskilt": "612_0", "vegvisningsskilt": "723_11",
    "underskilt": "807_1", "markeringsskilt": "902_0H",
}
THEMES = {
    "light": {"bg": (241, 243, 246), "card": (255, 255, 255), "track": (229, 232, 237), "text": (24, 26, 30),
              "hint": (120, 126, 136), "accent": (47, 123, 246), "soft": (176, 205, 251), "done": (52, 168, 83)},
    "dark": {"bg": (21, 22, 25), "card": (34, 35, 39), "track": (54, 56, 62), "text": (240, 241, 244),
             "hint": (150, 154, 162), "accent": (88, 150, 255), "soft": (52, 82, 130), "done": (76, 190, 106)},
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _thumb(sign_id: str, size: int) -> Image.Image | None:
    path = find_sign_image(sign_id)
    if not path:
        return None
    with Image.open(path) as img:
        img = img.convert("RGBA")
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        return img.copy()


def render(*, mastered: int, total: int, categories: list[tuple[str, int, int]],
           daily: list[int], goal: int, theme: str = "light") -> BytesIO:
    """categories: (code, learned, total); daily: answers per day, oldest first (14 values)."""
    c = THEMES.get(theme, THEMES["light"])
    img = Image.new("RGB", (W, H), c["bg"])
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, 500, 680), radius=36, fill=c["card"])
    d.rounded_rectangle((530, 40, 1240, 680), radius=36, fill=c["card"])

    # ring
    cx, cy, r, w = 270, 250, 160, 30
    box = (cx - r, cy - r, cx + r, cy + r)
    d.arc(box, 0, 360, fill=c["track"], width=w)
    share = mastered / total if total else 0
    if share > 0:
        d.arc(box, -90, -90 + 360 * share, fill=c["done"] if share >= 1 else c["accent"], width=w)
    pct = f"{round(share * 100)}%"
    d.text((cx, cy - 18), pct, font=_font(92), fill=c["text"], anchor="mm")
    d.text((cx, cy + 58), f"{mastered} / {total}", font=_font(34), fill=c["hint"], anchor="mm")

    # last 14 days against the goal
    x0, x1, y_top, y_base = 84, 456, 470, 640
    days = (daily + [0] * 14)[:14] if len(daily) < 14 else daily[-14:]
    peak = max([goal, *days, 1])
    step = (x1 - x0) / 14
    bar_w = step * 0.62
    goal_y = y_base - (y_base - y_top) * goal / peak
    for x in range(int(x0), int(x1), 14):
        d.line((x, goal_y, x + 7, goal_y), fill=c["hint"], width=2)
    for i, n in enumerate(days):
        left = x0 + i * step + (step - bar_w) / 2
        height = max(4, (y_base - y_top) * n / peak) if n else 4
        colour = c["accent"] if n >= goal else (c["soft"] if n else c["track"])
        d.rounded_rectangle((left, y_base - height, left + bar_w, y_base), radius=5, fill=colour)
    today = x0 + 13 * step + (step - bar_w) / 2
    d.rounded_rectangle((today - 4, y_top - 8, today + bar_w + 4, y_base + 4), radius=8, outline=c["hint"], width=2)

    # categories
    rows = sorted(categories, key=lambda r: -(r[1] / r[2] if r[2] else 0))[:9]
    top, row_h = 78, 66
    for i, (code, done, count) in enumerate(rows):
        y = top + i * row_h
        sign = _thumb(CATEGORY_SIGN.get(code, ""), 50)
        if sign:
            img.paste(sign, (572 + (50 - sign.width) // 2, y + (50 - sign.height) // 2), sign)
        bx0, bx1, by = 646, 1084, y + 16
        d.rounded_rectangle((bx0, by, bx1, by + 18), radius=9, fill=c["track"])
        part = done / count if count else 0
        if part > 0:
            d.rounded_rectangle((bx0, by, bx0 + max(18, (bx1 - bx0) * part), by + 18), radius=9,
                                fill=c["done"] if part >= 1 else c["accent"])
        d.text((1206, y + 25), f"{done}/{count}", font=_font(28), fill=c["text"], anchor="rm")

    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    out.seek(0)
    return out
