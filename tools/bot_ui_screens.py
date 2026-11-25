"""Fill the bot-ui map (bot-ui/) with screens rendered by the bot's own code.

`bot-ui import` reads the code statically, so computed texts (home screen, statistics,
theory list, my data, quiz cards) come out as placeholders. This script renders them with
the real functions on a demo learner and writes one bot-ui-patch/v1 file; the Studio and
the offline snapshot then show what the bot actually sends, without a bot token.

  py -3 tools/bot_ui_screens.py                 # writes bot-ui/.patches/rendered.json and applies it
  py -3 tools/bot_ui_screens.py --dry-run       # only checks the patch

Needs the telegram-bot-ui skill (TGUI env var or the default install path).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TGUI = Path(os.environ.get("TGUI", Path.home() / ".claude/skills/telegram-bot-ui/scripts/tgui.py"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "123456789:STUDIO-PREVIEW-NOT-A-REAL-TOKEN")
os.environ.setdefault("PAYWALL_ENABLED", "1")

import bot  # noqa: E402  (after the env defaults)
import keyboards as kb  # noqa: E402
import learning  # noqa: E402
import premium  # noqa: E402
from database import Database  # noqa: E402
from utils import find_sign_image, load_signs_list, process_sign_image  # noqa: E402


def tgui(*args: str) -> dict:
    out = subprocess.run([sys.executable, str(TGUI), "map", *args, "--project", str(ROOT / "bot-ui"), "--json"],
                         capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"tgui failed: {out.stdout}\n{out.stderr}")


def photo(sign_id: str) -> None:
    """The map accepts only https media Telegram can fetch; until the images are hosted the
    card's photo is named in the screen notes instead."""
    return None


def _unused_inline_photo(sign_id: str) -> dict:
    """A small inline picture of the real card, so the preview shows the sign."""
    from PIL import Image
    card = Image.open(process_sign_image(find_sign_image(sign_id), theme="light"))
    card.thumbnail((360, 360))
    buf = __import__("io").BytesIO()
    card.convert("RGB").save(buf, "JPEG", quality=80)
    return {"type": "photo", "file": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}


EXISTING: dict[str, dict] = {}   # callback_data -> action already on the imported map


def load_existing() -> dict[str, dict]:
    """Imported screens are the contract: a callback keeps the effect the importer recorded."""
    found = {}
    for f in sorted((ROOT / "bot-ui" / "screens").glob("main.*.json")):
        for act in (json.loads(f.read_text("utf-8")).get("actions") or {}).values():
            if act.get("callbackData") and act["callbackData"] not in found:
                found[act["callbackData"]] = act
    return found


def actions_from(markup, routes: dict[str, str]) -> tuple[dict, list]:
    """bot-ui actions and rows from a real InlineKeyboardMarkup. routes: callback_data -> screen."""
    actions, rows = {}, []
    for r, row in enumerate(markup.inline_keyboard):
        ids = []
        for c, b in enumerate(row):
            aid = f"b{r}{c}"
            act: dict = {"label": {"uk": b.text}}
            if b.url or b.web_app:
                act.update(type="url", url=b.url or b.web_app.url)
            elif b.callback_data in EXISTING and b.callback_data != "study_next":
                act.update({k: v for k, v in EXISTING[b.callback_data].items()
                            if k in ("type", "to", "presentation", "text", "rule", "handlerId", "outcomes")})
            elif b.callback_data in routes:
                act.update(type="navigate", to=routes[b.callback_data], presentation="edit")
            else:
                act.update(type="answer", text={"uk": "Відкривається в боті"})
            if b.callback_data:
                act["callbackData"] = b.callback_data
            if b.style:
                act["style"] = b.style
            actions[aid] = act
            ids.append(aid)
        rows.append(ids)
    return actions, rows


def screen(sid: str, title: str, kind: str, text: str, markup=None, routes=None, media=None, notes="") -> dict:
    doc = {"id": sid, "title": title, "kind": kind, "audience": "private",
           "notes": notes or "rendered by tools/bot_ui_screens.py from the bot's own functions",
           "message": {"id": "main", "format": "regular.html", "text": {"uk": text}}}
    if media:
        doc["message"]["media"] = media
    if markup is not None:
        actions, rows = actions_from(markup, routes or {})
        doc["keyboard"] = {"type": "inline", "rows": rows}
        doc["actions"] = actions
    return doc


def build() -> list[dict]:
    tmp = tempfile.mkdtemp()
    db = Database(os.path.join(tmp, "studio.db"))
    db.init_db()
    uid = 1001
    db.upsert_user(uid, "no", "uk")
    db.touch_identity(uid, first_name="Olena", last_name=None, username="olena_k", language_code="uk", is_premium=False)
    db.update_profile(uid, {"exam_date": time.strftime("%Y-%m-%d", time.localtime(time.time() + 22 * 86400))})
    valid = [s for s in load_signs_list() if s in bot.signs_main]
    now = int(time.time())
    for i, s in enumerate(valid[:60]):
        db.set_box(uid, s, 5 if i < 40 else 1, now + 86400 if i < 51 else now - 60)
    bot.db, bot.VALID_SIGNS, premium_db = db, valid, db
    user = db.get_user(uid)

    home_text, home_kb = bot.home_screen(user, "Olena")
    routes = {"study_next": "studio.study.intro", "home_theory": "studio.theory", "home_stats": "studio.stats",
              "home_categories": "studio.categories", "home_settings": "studio.settings", "premium_open": "studio.premium",
              "home_open": "studio.home", "settings_back": "studio.settings", "data_show": "studio.mydata",
              "data_delete": "studio.mydata.delete", "q|302_0|302_0": "studio.study.right",
              "q|302_0|100_1": "studio.study.wrong", "q|302_0|204_0": "studio.study.wrong",
              "q|302_0|206_0": "studio.study.wrong", "more|302_0": "studio.study.more", "know|100_1": "studio.study.quiz"}

    intro_text = bot.intro_card_text("100_1", "no", "uk")
    quiz_text = "❓ <b>Що означає цей знак?</b>\n\n🔁 Повторення • рівень 2/6"
    quiz_kb = kb.get_quiz_keyboard("302_0", ["302_0", "100_1", "204_0", "206_0"], bot.signs_main, "no")
    right = ("✅ <b>Правильно</b>\n\n" + bot.sign_name_block("302_0", "no", "uk")
             + "\nРівень: 3/6 · повторення через 3 дн")
    wrong = ("❌ <b>Неправильно</b>\n\nПравильна відповідь:\n" + bot.sign_name_block("302_0", "no", "uk")
             + f"\n{bot.h(bot.signs_main['302_0']['descriptions']['no'])}\n\nЦей знак повториться за кілька хвилин.")
    extra = bot.signs_extra.get("302_0", {}).get("extra", {})
    more = f"ℹ️ <b>{bot.h(bot.signs_main['302_0']['names']['no'])}</b>\n\n{bot.h(extra.get('no', ''))}\n\n<i>{bot.h(extra.get('uk', ''))}</i>"

    progress = db.get_progress_map(uid)
    stats_text = bot.build_statistics_text(
        mastered=sum(1 for p in progress.values() if p["box"] >= learning.MASTERED_BOX), total=len(valid),
        in_learning=sum(1 for p in progress.values() if p["box"] < learning.MASTERED_BOX),
        new=len(valid) - len(progress), due_now=sum(1 for p in progress.values() if p["next_review_at"] <= now),
        answered=180, correct_total=151, today_answered=12, today_correct=10, streak=4,
        category_rows=[("Попереджувальні знаки", 25, 48), ("Заборонні знаки", 15, 48), ("Інформаційні знаки", 0, 48)])
    prem_text, prem_kb = premium.screen(premium_db, uid, "https://t.me/$demo-invoice")

    return [
        screen("studio.home", "Головна (повернення)", "entry", home_text, home_kb, routes),
        screen("studio.study.intro", "Навчання: новий знак", "menu", intro_text, kb.get_intro_keyboard("100_1"), routes,
               notes="photo card of sign 100_1 (data/cutouts) with this caption; the next card replaces it in the same message (editMessageMedia)"),
        screen("studio.study.quiz", "Навчання: квіз", "form", quiz_text, quiz_kb, routes, notes="photo card of sign 302_0 with this caption"),
        screen("studio.study.right", "Квіз: правильно", "result", right, kb.get_feedback_keyboard("302_0"), routes, notes="caption edit of the quiz card"),
        screen("studio.study.wrong", "Квіз: помилка", "result", wrong, kb.get_feedback_keyboard("302_0"), routes, notes="caption edit of the quiz card"),
        screen("studio.study.more", "Пояснення знака", "result", more, kb.get_details_keyboard(), routes),
        screen("studio.theory", "Теорія і тести", "menu", bot.theory_screen_text("B"), kb.get_theory_keyboard("https://example.app/"), routes),
        screen("studio.stats", "Статистика (текстова версія)", "result", stats_text, None,
               notes="the bot sends this as a Rich Message with three tables; this is its HTML fallback"),
        screen("studio.categories", "Категорії", "form",
               "📂 <b>Категорії для навчання</b>\n\nТоркніться категорії, щоб увімкнути або вимкнути її.\n✓ — обрано · ○ — не обрано\n\nЗміни зберігаються одразу.",
               kb.get_categories_keyboard(bot.signs_main, "no", "fareskilt,forbudsskilt", valid), routes),
        screen("studio.settings", "Налаштування (текстова версія)", "menu", bot.build_settings_text(user), kb.get_settings_keyboard(), routes),
        screen("studio.premium", "Преміум: оформлення", "menu", prem_text, prem_kb, routes),
        screen("studio.mydata", "Мої дані", "result", bot.mydata_text(db.get_user(uid)), kb.get_mydata_keyboard(), routes),
        screen("studio.mydata.delete", "Видалення даних: підтвердження", "confirmation", bot.delete_prompt_text(),
               kb.get_delete_confirm_keyboard(), routes),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    EXISTING.update(load_existing())
    docs = build()
    listing = tgui("list")
    existing = {s["id"] for s in listing.get("screens", [])}
    revision = listing["revision"]
    changes = []
    for doc in docs:
        if doc["id"] in existing:
            ops = [{"op": "set", "path": f"/{k}", "value": doc[k]} for k in ("title", "kind", "notes", "message", "keyboard", "actions") if k in doc]
            changes.append({"screenId": doc["id"], "ops": ops})
        else:
            changes.append({"screenId": doc["id"], "create": doc})
    # «Продовжити навчання» everywhere opens the study card (the same effect for one callback)
    for f in sorted((ROOT / "bot-ui" / "screens").glob("main.*.json")):
        sdoc = json.loads(f.read_text("utf-8"))
        ops = [{"op": "set", "path": f"/actions/{aid}/to", "value": "studio.study.intro"}
               for aid, act in (sdoc.get("actions") or {}).items()
               if act.get("callbackData") == "study_next" and act.get("to") != "studio.study.intro"]
        ops += [{"op": "set", "path": f"/actions/{aid}/type", "value": "navigate"}
                for aid, act in (sdoc.get("actions") or {}).items()
                if act.get("callbackData") == "study_next" and act.get("type") != "navigate"]
        if ops:
            changes.append({"screenId": sdoc["id"], "ops": ops})
    patch = {"format": "bot-ui-patch/v1", "projectId": "road-sign-bot", "baseRevision": revision, "changes": changes}
    out = ROOT / "bot-ui" / ".patches" / "rendered.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(patch, ensure_ascii=False, indent=1), "utf-8")
    flags = ["--dry-run"] if args.dry_run else []
    result = subprocess.run([sys.executable, str(TGUI), "map", "apply-patch", "--patch-file", str(out), "--project", str(ROOT / "bot-ui"), *flags],
                            capture_output=True, text=True, encoding="utf-8")
    print(result.stdout.strip() or result.stderr.strip())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
