"""Audit the sign database: ids, images, languages and text quality.

Read-only. Prints a Markdown report (or writes it with --out). Checks:
  - ids agree across signs_main.json, signs_extra.json, signs_list.txt and images
  - every record has names, descriptions and extra text in all four languages
  - text in the wrong script, empty or very short texts, untranslated copies
  - duplicate names in one language (two right answers in a quiz)
  - names too long for a quiz button, cards too long for a photo caption
  - near-identical descriptions shared by many signs (template text that teaches nothing)

Run: py -3 tools/audit_data.py [--out docs/audit/data-audit.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LANGS = ("no", "en", "uk", "ru")
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN = re.compile(r"[A-Za-zÆØÅæøå]")
QUIZ_BUTTON_MAX = 48      # keyboards.MAX_OPTION_LEN
CAPTION_MAX = 1024


def load():
    main = json.loads((DATA / "signs_main.json").read_text("utf-8"))
    extra = json.loads((DATA / "signs_extra.json").read_text("utf-8"))
    listed = [l.strip() for l in (DATA / "signs_list.txt").read_text("utf-8").splitlines() if l.strip()]
    images = {p.stem: p.name for p in (DATA / "images").iterdir() if p.is_file()}
    return main, extra, listed, images


def normalize_id(sign_id: str) -> str:
    """Spelling-insensitive key: letter O for zero, dot for underscore."""
    return sign_id.replace("O", "0").replace(".", "_")


def script_ok(lang: str, text: str) -> bool:
    if lang in ("uk", "ru"):
        return bool(CYRILLIC.search(text))
    return not CYRILLIC.search(text)


def audit() -> tuple[str, int]:
    main, extra, listed, images = load()
    out: list[str] = []
    problems = 0

    def section(title: str, rows: list[str]):
        nonlocal problems
        out.append(f"\n## {title} ({len(rows)})\n")
        out.extend(f"- {r}" for r in rows) if rows else out.append("- none")
        problems += len(rows)

    out.append("# Sign database audit\n")
    out.append(f"Records: {len(main)} in signs_main, {len(extra)} in signs_extra, "
               f"{len(listed)} in signs_list, {len(images)} image files.")

    # ---- ids ----
    rows = []
    for k, v in main.items():
        if v.get("id") != k:
            rows.append(f"`{k}`: field id is `{v.get('id')}`")
    section("Record key differs from its id field", rows)

    by_norm_img = {normalize_id(s): s for s in images}
    rows, fixable = [], []
    for k in sorted(main):
        if k in images:
            continue
        alt = by_norm_img.get(normalize_id(k))
        if alt:
            fixable.append(f"`{k}` → image `{images[alt]}` (spelling differs)")
        else:
            rows.append(f"`{k}` {main[k]['names']['no']}")
    section("Records with an image under a different spelling", fixable)
    section("Records with no image at all", rows)

    norm_main = {normalize_id(k) for k in main}
    rows = [f"`{images[s]}`" for s in sorted(images)
            if s not in main and normalize_id(s) not in norm_main]
    section("Images with no record (candidates to describe and add)", rows)

    section("In signs_main but not in signs_list", [f"`{k}`" for k in sorted(set(main) - set(listed))])
    section("In signs_list but not in signs_main", [f"`{k}`" for k in listed if k not in main])
    section("No extended explanation (signs_extra)", [f"`{k}` {main[k]['names']['no']}"
                                                      for k in sorted(set(main) - set(extra))])

    # ---- languages and scripts ----
    missing, wrong_script, short, same = [], [], [], []
    for k, v in sorted(main.items()):
        fields = {"name": v.get("names", {}), "description": v.get("descriptions", {}),
                  "extra": extra.get(k, {}).get("extra", {}) if k in extra else None}
        for field, texts in fields.items():
            if texts is None:
                continue
            for lang in LANGS:
                t = (texts.get(lang) or "").strip()
                if not t:
                    missing.append(f"`{k}` {field}.{lang}")
                    continue
                if not script_ok(lang, t):
                    wrong_script.append(f"`{k}` {field}.{lang}: {t[:70]}")
                if field == "description" and len(t) < 25:
                    short.append(f"`{k}` description.{lang}: “{t}”")
            if texts.get("no") and texts.get("no") == texts.get("en"):
                same.append(f"`{k}` {field}: no == en “{texts['no'][:60]}”")
            if texts.get("uk") and texts.get("uk") == texts.get("ru"):
                same.append(f"`{k}` {field}: uk == ru “{texts['uk'][:60]}”")
    section("Missing translations", missing)
    section("Text in the wrong script", wrong_script)
    section("Very short descriptions", short)
    section("Identical text in two languages (untranslated?)", same)

    # ---- quiz quality ----
    rows = []
    for lang in ("no", "en"):
        names = defaultdict(list)
        for k, v in main.items():
            names[v["names"].get(lang, "").strip().lower()].append(k)
        for name, ids in sorted(names.items()):
            if len(ids) > 1:
                rows.append(f"{lang}: “{name}” — {', '.join(f'`{i}`' for i in sorted(ids))}")
    section("Same name for different signs (ambiguous quiz answers)", rows)

    rows = [f"`{k}` {lang} ({len(v['names'][lang])}): {v['names'][lang]}"
            for k, v in sorted(main.items()) for lang in ("no", "en")
            if len(v["names"].get(lang, "")) > QUIZ_BUTTON_MAX]
    section(f"Names longer than a quiz button ({QUIZ_BUTTON_MAX} chars, get cut with …)", rows)

    rows = []
    for k, v in sorted(main.items()):
        for study in ("no", "en"):
            for trans in LANGS:
                if trans == study:
                    continue
                n = sum(len(v[f].get(l, "")) for f in ("names", "descriptions") for l in (study, trans)) + 40
                if n > CAPTION_MAX:
                    rows.append(f"`{k}` {study}+{trans}: ~{n} chars")
    section("Intro cards longer than a photo caption", rows)

    # ---- template descriptions ----
    stems = Counter()
    owners = defaultdict(list)
    for k, v in main.items():
        d = v["descriptions"].get("en", "")
        stem = re.sub(r"\W+", " ", d.lower()).strip()
        stems[stem] += 1
        owners[stem].append(k)
    rows = [f"{n}× “{s[:80]}” — {', '.join(sorted(owners[s])[:8])}" for s, n in stems.most_common() if n > 1]
    section("Descriptions repeated word for word (en)", rows)

    # ---- categories ----
    cats = defaultdict(set)
    for v in main.values():
        cats[v["category_code"]].add(json.dumps(v["category"]["names"], ensure_ascii=False, sort_keys=True))
    rows = [f"`{c}` has {len(n)} different name sets" for c, n in cats.items() if len(n) > 1]
    section("Category names inconsistent", rows)
    counts = Counter(v["category_code"] for v in main.values())
    out.append("\n## Records per category\n")
    out.extend(f"- `{c}`: {n}" for c, n in counts.most_common())

    return "\n".join(out) + "\n", problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    report, problems = audit()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, "utf-8")
        print(f"wrote {args.out} ({problems} items)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
