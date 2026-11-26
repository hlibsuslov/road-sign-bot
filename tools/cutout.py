"""Cut the white background out of the sign library.

The source files in data/images/ are the official sign artwork: tightly cropped to the
sign, with a thin contour line as the outermost ring and plain white paper outside the
shape. So the background is exactly the near-white area that is connected to the image
border without crossing a non-white pixel. That rule works the same for every shape
(triangle, circle, octagon, diamond, rounded rectangle, arrow-shaped direction signs):
the white rim and white face inside the contour are never connected to the border.

Steps per image:
  1. Colour: CMYK without a profile is converted through a European press profile
     (Coated FOGRA39) instead of Pillow's naive formula, which turns greens neon.
     RGB with an embedded profile is converted to sRGB.
  2. Mask at full resolution: near-white pixels, minus a 1 px band around anything
     non-white (closes anti-aliasing gaps in the contour), flood-filled from the border.
     The band is then given back to the background where it is near-white.
  3. Specks are dropped, holes inside the sign are kept as sign.
  4. Downscale premultiplied, so edges get soft alpha without a white halo.
  5. QA: shape class from fill ratio and solidity, and flags for anything unusual
     (white sign faces touching the border, removed area that doesn't fit a shape).

Output: data/cutouts/<id>.webp (lossless RGBA, longest side <= --size),
data/cutouts/thumb/<id>.webp (256 px preview) and data/cutouts/manifest.json. Run: py -3 tools/cutout.py [--only 100_1,302_0] [--sheet qa.png]

Dev-only dependencies: numpy, scipy (tools/requirements.txt). The bot itself only
reads the finished WebP files.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageDraw
from scipy import ndimage
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "images"
OUT = ROOT / "data" / "cutouts"
DEFAULT_CMYK_PROFILE = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / \
    "System32" / "spool" / "drivers" / "color" / "CoatedFOGRA39.icc"

PAPER_MIN = 254      # background paper is pure white
WHITE_MIN = 232      # anti-aliased fringe next to the paper
WHITE_SPREAD = 24    # ... and nearly grey (max - min channel)
COLOR_MATCH = 60     # two pixels belong to the same printed layer
SPECK_FRACTION = 0.002


def to_srgb(img: Image.Image, cmyk_profile: Path | None) -> Image.Image:
    """Return RGBA in sRGB, keeping existing transparency."""
    srgb = ImageCms.createProfile("sRGB")
    icc = img.info.get("icc_profile")
    if img.mode == "CMYK":
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc)) if icc else (
            ImageCms.getOpenProfile(str(cmyk_profile)) if cmyk_profile else None)
        if src is None:
            return img.convert("RGBA")
        rgb = ImageCms.profileToProfile(img, src, srgb, outputMode="RGB",
                                        renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
        return rgb.convert("RGBA")
    alpha = img.getchannel("A") if "A" in img.getbands() else None
    rgb = img.convert("RGB")
    if icc:
        try:
            rgb = ImageCms.profileToProfile(rgb, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                            srgb, outputMode="RGB")
        except ImageCms.PyCMSError:
            pass
    out = rgb.convert("RGBA")
    if alpha is not None:
        out.putalpha(alpha)
    return out


def _flood_background(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """Paper connected to the border. Paper is pure white (255): the sign's own white
    is printed slightly grey (249-252), so a strict test keeps rims and faces even
    where the contour line is faint."""
    paper = ((rgb.min(axis=2) >= PAPER_MIN) & (rgb.max(axis=2) - rgb.min(axis=2) <= 3)) | ~opaque
    barrier = ndimage.binary_dilation(~paper, structure=np.ones((3, 3), bool))
    free = paper & ~barrier
    labels, _ = ndimage.label(np.pad(free, 1, constant_values=True))
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bg = np.isin(labels, border[border != 0])[1:-1, 1:-1]
    # Give the closing band back, plus the anti-aliased fringe next to the paper.
    near_white = (rgb.min(axis=2) >= WHITE_MIN) & (rgb.max(axis=2) - rgb.min(axis=2) <= WHITE_SPREAD)
    bg |= ndimage.binary_dilation(bg, structure=np.ones((3, 3), bool)) & (paper | near_white)
    return bg


def _close(a: np.ndarray, b: np.ndarray) -> bool:
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max()) < COLOR_MATCH


def _corner_radius(rgb: np.ndarray, flip_y: bool, flip_x: bool) -> int:
    """Outline radius of one corner of a frame-filling rectangular sign.

    The artwork often has square bleed outside a rounded rim (blue corners outside the
    white rim of 502, 601) or a square rim around a rounded border (548). Walk inward
    from the middle of the adjacent edge to find the first layer boundary after the rim
    (at depth e), then walk the diagonal to find the same boundary (at d). A boundary
    rounded with radius R meets the diagonal at e + R(1 - 1/sqrt 2); the sign outline is
    concentric with it, so its radius is R + e. Square layers give d == e, radius 0.
    """
    img = rgb[::-1] if flip_y else rgb
    img = img[:, ::-1] if flip_x else img
    h, w = img.shape[:2]
    limit = int(min(h, w) * 0.25)
    radii = []
    for edge in (img[:limit, w // 2], img[h // 2, :limit]):
        start = next((i for i in range(min(4, limit)) if not _close(edge[i], edge[0])), 0)
        start = start if start and start <= 3 else 0          # skip a 1-3 px contour
        rim = edge[start]
        e = next((i for i in range(start, limit) if not _close(edge[i], rim)), None)
        if e is None:
            continue
        nxt = edge[min(e + 2, limit - 1)]
        diag = np.array([img[t, t] for t in range(limit)])
        seen_rim = next((t for t in range(limit) if _close(diag[t], rim)), None)
        if seen_rim is None:
            continue
        d = next((t for t in range(seen_rim, limit) if _close(diag[t], nxt)), None)
        if d is None or d <= e + 1:
            radii.append(0)
            continue
        radii.append(int(round((d - e) / (1 - 2 ** -0.5) + e)))
    if not radii:
        return 0
    r = int(np.median(radii))
    return r if r <= limit else 0


def _round_corners(keep: np.ndarray, rgb: np.ndarray) -> list[int]:
    h, w = keep.shape
    yy, xx = np.ogrid[:h, :w]
    radii = []
    for fy in (False, True):
        for fx in (False, True):
            r = _corner_radius(rgb, fy, fx)
            radii.append(r)
            if r < 3:
                continue
            cy = (h - 1 - r) if fy else r
            cx = (w - 1 - r) if fx else r
            in_corner = ((yy > cy) if fy else (yy < cy)) & ((xx > cx) if fx else (xx < cx))
            keep &= ~(in_corner & ((yy - cy) ** 2 + (xx - cx) ** 2 > r * r))
    return radii


def sign_mask(rgba: np.ndarray, force: str | None = None) -> tuple[np.ndarray, dict]:
    """Boolean mask of the sign (True = keep) and how it was found.

    force: "flood" or "full-frame" from tools/cutout_overrides.json, for the few files a
    human checked on the QA sheet where the automatic choice is wrong."""
    rgb = rgba[..., :3]
    opaque = rgba[..., 3] >= 128
    info = {"had_alpha": bool(rgba[..., 3].min() < 250)}
    bg = _flood_background(rgb.astype(np.int16), opaque)

    keep = ~bg
    labels, n = ndimage.label(keep)
    if n > 1:
        sizes = ndimage.sum(keep, labels, index=range(1, n + 1))
        big = [i + 1 for i, s in enumerate(sizes) if s >= SPECK_FRACTION * keep.size]
        keep = np.isin(labels, big)
    keep = ndimage.binary_fill_holes(keep)

    h, w = keep.shape
    removed = 1 - keep.mean()
    ys, xs = np.nonzero(keep)
    spans_frame = len(xs) and (xs.max() - xs.min() + 1) >= 0.98 * w and \
        (ys.max() - ys.min() + 1) >= 0.98 * h
    shape = classify(keep)["shape"] if len(xs) else "empty"

    if force:
        info["override"] = force
    if force == "flood":
        info["method"] = "flood"
    elif force == "full-frame" or removed < 0.01 or \
            (spans_frame and shape in {"rectangle", "rounded-rectangle", "irregular"}):
        # The sign fills the frame. Anything the flood took outside the corners is the
        # sign's own white (striped marker posts 914, 920): keep the whole rectangle,
        # then cut rounded corners from the artwork's own geometry.
        corner = int(min(h, w) * 0.12)
        zone = np.zeros_like(keep)
        zone[:corner, :corner] = zone[:corner, -corner:] = True
        zone[-corner:, :corner] = zone[-corner:, -corner:] = True
        outside_corners = (~keep & ~zone).mean()
        if force == "full-frame" or outside_corners > 0.002:
            info["method"] = "full-frame"
            keep = opaque.copy()
        else:
            info["method"] = "frame+corners"
            keep = keep & opaque
        info["corner_radii"] = _round_corners(keep, rgb)
    else:
        info["method"] = "flood"
    return keep, info


def classify(mask: np.ndarray) -> dict:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return {"shape": "empty", "fill": 0.0, "solidity": 0.0}
    h = ys.max() - ys.min() + 1
    w = xs.max() - xs.min() + 1
    area = len(xs)
    fill = area / float(w * h)
    step = max(1, len(xs) // 20000)
    pts = np.column_stack([xs[::step], ys[::step]]).astype(float)
    try:
        hull = ConvexHull(pts).volume
        solidity = min(1.0, area / hull) if hull else 0.0
    except Exception:
        solidity = 0.0
    aspect = w / float(h)
    if fill > 0.97:
        shape = "rectangle"
    elif 0.9 < fill <= 0.97:
        shape = "rounded-rectangle"
    elif 0.8 <= fill <= 0.9 and 0.9 < aspect < 1.1:
        shape = "octagon"
    elif 0.74 <= fill < 0.8 and 0.9 < aspect < 1.1:
        shape = "circle"
    elif 0.44 <= fill < 0.56 and solidity > 0.95:
        shape = "triangle-or-diamond"
    else:
        shape = "irregular"
    return {"shape": shape, "fill": round(fill, 3), "solidity": round(solidity, 3),
            "aspect": round(aspect, 3)}


def flags_for(info: dict, removed: float) -> list[str]:
    if info.get("override"):
        return []           # a human checked this file on the QA sheet
    flags = []
    if info["shape"] == "irregular" and info["method"] == "flood":
        flags.append("irregular-shape")
    if info["solidity"] and info["solidity"] < 0.95 and info["method"] == "flood":
        flags.append("low-solidity")
    if info["method"] == "full-frame":
        flags.append("kept-full-frame")
    if removed > 0.6:
        flags.append("large-removal")
    return flags


def cut(path: Path, size: int, cmyk_profile: Path | None,
        force: str | None = None) -> tuple[Image.Image, dict]:
    with Image.open(path) as src:
        rgba = to_srgb(src, cmyk_profile)
    arr = np.asarray(rgba).copy()
    mask, info = sign_mask(arr, force)
    arr[..., 3] = np.where(mask, np.minimum(arr[..., 3], 255) if info["had_alpha"] else 255, 0)
    out = Image.fromarray(arr, "RGBA")
    bbox = out.getchannel("A").getbbox()
    if bbox:
        out = out.crop(bbox)
    scale = size / max(out.size)
    if scale < 1:
        new = (max(1, round(out.width * scale)), max(1, round(out.height * scale)))
        out = out.convert("RGBa").resize(new, Image.Resampling.LANCZOS).convert("RGBA")
    removed = 1.0 - mask.mean()
    info.update(classify(mask))
    info["removed"] = round(removed, 3)
    info["size"] = list(out.size)
    info["flags"] = flags_for(info, removed)
    return out, info


THUMB_SIZE = 256


def save_thumb(img: Image.Image, sign_id: str) -> None:
    """Small lossy preview for lists and grids (the Mini App library)."""
    thumb = img.copy()
    thumb.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
    (OUT / "thumb").mkdir(parents=True, exist_ok=True)
    thumb.save(OUT / "thumb" / f"{sign_id}.webp", "WEBP", quality=88, method=6)


def qa_sheet(items: list[tuple[str, Image.Image, dict]], path: Path, tile: int = 180) -> None:
    """Each cutout on a light and a dark tile, so halos and eaten rims are visible."""
    cols = 6
    rows = (len(items) + cols - 1) // cols
    cell_w, cell_h = tile * 2, tile + 18
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (200, 200, 200))
    draw = ImageDraw.Draw(sheet)
    for i, (sid, img, info) in enumerate(items):
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        for j, bg in enumerate([(255, 255, 255), (33, 33, 36)]):
            tile_img = Image.new("RGB", (tile, tile), bg)
            thumb = img.copy()
            thumb.thumbnail((tile - 16, tile - 16))
            tile_img.paste(thumb, ((tile - thumb.width) // 2, (tile - thumb.height) // 2), thumb)
            sheet.paste(tile_img, (x + j * tile, y))
        label = f"{sid} {info['shape']} {' '.join(info['flags'])}"
        draw.text((x + 3, y + tile + 3), label, fill=(160, 0, 0) if info["flags"] else (0, 0, 0))
    sheet.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", help="comma-separated image ids")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--cmyk-profile", type=Path, default=DEFAULT_CMYK_PROFILE)
    ap.add_argument("--sheet", type=Path, help="write a QA contact sheet here")
    ap.add_argument("--dry-run", action="store_true", help="don't write cutouts")
    ap.add_argument("--thumbs-only", action="store_true", help="rebuild previews from existing cutouts")
    args = ap.parse_args()

    if args.thumbs_only:
        for path in sorted(OUT.glob("*.webp")):
            with Image.open(path) as img:
                save_thumb(img, path.stem)
        print(f"{len(list((OUT / 'thumb').glob('*.webp')))} previews")
        return 0

    profile = args.cmyk_profile if args.cmyk_profile.exists() else None
    if profile is None:
        print(f"warning: CMYK profile not found at {args.cmyk_profile}; naive conversion",
              file=sys.stderr)
    wanted = set(args.only.split(",")) if args.only else None
    files = sorted(p for p in SRC.iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
                   and (wanted is None or p.stem in wanted))
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}

    overrides_path = Path(__file__).with_name("cutout_overrides.json")
    overrides = json.loads(overrides_path.read_text("utf-8")) if overrides_path.exists() else {}

    items = []
    for p in files:
        force = overrides.get(p.stem, {}).get("method")
        img, info = cut(p, args.size, profile, force)
        if force:
            info["override"] = overrides[p.stem]
        info["source"] = p.name
        manifest[p.stem] = info
        items.append((p.stem, img, info))
        if not args.dry_run:
            img.save(OUT / f"{p.stem}.webp", "WEBP", lossless=True, quality=100, method=6)
            save_thumb(img, p.stem)
        mark = " FLAG " + ",".join(info["flags"]) if info["flags"] else ""
        print(f"{p.stem:10} {info['shape']:20} removed={info['removed']:.3f}{mark}")

    if not args.dry_run:
        manifest_path.write_text(
            json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=1) + "\n",
            "utf-8")
    if args.sheet:
        page = 48
        for n, i in enumerate(range(0, len(items), page), start=1):
            target = args.sheet if len(items) <= page else \
                args.sheet.with_name(f"{args.sheet.stem}-{n:02}{args.sheet.suffix}")
            qa_sheet(items[i:i + page], target)
    flagged = sum(1 for _, _, i in items if i["flags"])
    print(f"{len(items)} images, {flagged} flagged for review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
