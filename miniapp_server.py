"""HTTP side of the Mini App: static files, sign images and a small JSON API.

Runs in the bot's own event loop (aiohttp ships with aiogram), so the app and the chat
share one SQLite database and one copy of the sign catalogue.

  GET /                      Mini App (webapp/index.html)
  GET /dist/*, /_kit/*       built scripts and the UI kit
  GET /signs/<id>.webp       transparent sign image from data/cutouts
  GET /signs/thumb/<id>.webp 256 px preview for lists
  GET /api/catalog           public: categories and signs (names, texts, shape, scale)
  GET /api/me                private: settings, progress, premium status, recent tests
  GET /api/study/next        private, premium: next step of the Leitner loop (same as chat)
  POST /api/study/seen|known|answer
  POST /api/exam/start       private, premium: a timed test; answers stay on the server
  GET /api/exam/<id>/<n>.webp  question image by position (the URL doesn't name the sign)
  POST /api/exam/finish      grade once, store, send the result to the chat
  POST /api/premium/invoice  Stars subscription link for Telegram.WebApp.openInvoice

Private endpoints trust nothing from the client except initData, checked with the bot
token (HMAC, references/mini-apps/security.md): `Authorization: tma <initData>`.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import secrets
import time
from pathlib import Path

from aiohttp import web

import learning
import premium
from init_data import InitDataError, verify_hmac
from utils import cutout_manifest, sign_scale

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent
WEBAPP = BASE / "webapp"
CUTOUTS = BASE / "data" / "cutouts"
SIGN_ID = re.compile(r"[0-9]{3}_[0-9A-Z]{1,4}")
EXAM_ID = re.compile(r"[A-Za-z0-9_-]{22}")
INIT_DATA_MAX_AGE = 24 * 3600   # learning data; the invoice itself is checked by Telegram
EXAM_SIZES = (10, 20, 45)       # 45 = the real teoriprøven length
EXAM_SECONDS_PER_QUESTION = 60
EXAM_PASS_RATIO = 38 / 45       # teoriprøven klasse B: at most 7 mistakes out of 45


def build_catalog(signs_main: dict, signs_extra: dict, valid: list[str]) -> dict:
    manifest = cutout_manifest()
    categories: dict[str, dict] = {}
    signs = []
    for sign_id in valid:
        sign = signs_main.get(sign_id)
        if not sign:
            continue
        code = sign["category_code"]
        categories.setdefault(code, {"code": code, "names": sign["category"]["names"], "count": 0})
        categories[code]["count"] += 1
        signs.append({
            "id": sign_id,
            "number": sign_id.split("_")[0],
            "category": code,
            "shape": manifest.get(sign_id, {}).get("shape"),
            "scale": sign_scale(sign_id),
            "names": sign["names"],
            "descriptions": sign["descriptions"],
            "extra": signs_extra.get(sign_id, {}).get("extra", {}),
        })
    return {"categories": sorted(categories.values(), key=lambda c: c["code"]), "signs": signs}


def create_app(*, db, bot_token: str, get_catalog, signs_main: dict, get_valid,
               bot=None) -> web.Application:
    """get_catalog() and get_valid() return the catalogue and the sign ids with images,
    built after the image check at startup. bot (optional) creates invoice links and
    sends test results to the chat."""
    app = web.Application(client_max_size=64 * 1024)

    def user_id_from(request: web.Request) -> int:
        header = request.headers.get("Authorization", "")
        if not header.startswith("tma "):
            raise web.HTTPUnauthorized(text="missing initData")
        try:
            fields = verify_hmac(header[4:], bot_token, max_age=INIT_DATA_MAX_AGE)
        except InitDataError as exc:
            logger.info("Mini App: initData rejected (%s)", exc)
            raise web.HTTPUnauthorized(text="invalid initData")
        user = fields.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise web.HTTPUnauthorized(text="no user in initData")
        return user["id"]

    def json_error(exc_class, code: str):
        return exc_class(text=json.dumps({"error": code}), content_type="application/json")

    def registered_user(user_id: int):
        user = db.get_user(user_id)
        if user is None:
            raise json_error(web.HTTPConflict, "not_registered")
        return user

    def require_premium(user_id: int) -> None:
        if not premium.is_premium(db, user_id):
            raise json_error(web.HTTPPaymentRequired, "premium_required")

    async def body(request: web.Request) -> dict:
        try:
            data = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise web.HTTPBadRequest(text="JSON body expected")
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="JSON object expected")
        return data

    def valid_sign(value) -> str:
        if not isinstance(value, str) or value not in set(get_valid()):
            raise web.HTTPBadRequest(text="unknown sign")
        return value

    def pool_for(user) -> list[str]:
        valid = get_valid()
        cats = user["selected_category"] or "all"
        if cats == "all":
            return list(valid)
        selected = set(cats.split(","))
        return [s for s in valid if signs_main.get(s, {}).get("category_code") in selected]

    def no_store(data: dict) -> web.Response:
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    async def index(_):
        return web.FileResponse(WEBAPP / "index.html", headers={"Cache-Control": "no-cache"})

    async def stylesheet(_):
        return web.FileResponse(WEBAPP / "app.css", headers={"Cache-Control": "no-cache"})

    async def sign_image(request: web.Request):
        sign_id = request.match_info["sign_id"]
        folder = CUTOUTS / "thumb" if request.match_info.get("size") == "thumb/" else CUTOUTS
        path = folder / f"{sign_id}.webp"
        if not SIGN_ID.fullmatch(sign_id) or not path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})

    async def catalog(_):
        return web.json_response(get_catalog(), headers={"Cache-Control": "public, max-age=300"})

    async def me(request: web.Request):
        user_id = user_id_from(request)
        user = db.get_user(user_id)
        if user is None:
            return web.json_response({"registered": False})
        now = int(time.time())
        progress = {
            sign_id: {"box": row["box"], "due": row["next_review_at"] <= now,
                      "correct": row["correct_count"], "wrong": row["wrong_count"]}
            for sign_id, row in db.get_progress_map(user_id).items()
        }
        answered, correct = db.get_answer_totals(user_id)
        return web.json_response({
            "registered": True,
            "study_language": user["study_language"],
            "translation_language": user["translation_language"],
            "mastered_box": learning.MASTERED_BOX,
            "max_box": learning.MAX_BOX,
            "answered": answered,
            "correct": correct,
            "streak": learning.count_streak(db.get_active_days(user_id)),
            "progress": progress,
            "pool": len(pool_for(user)),
            "premium": premium.status(db, user_id),
            "exams": [{"correct": r["correct"], "total": r["total"], "finished_at": r["finished_at"],
                       "passed": r["correct"] >= r["total"] * EXAM_PASS_RATIO}
                      for r in db.recent_exams(user_id)],
        }, headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------ learning (the chat's loop)

    async def study_next(request: web.Request):
        user_id = user_id_from(request)
        user = registered_user(user_id)
        require_premium(user_id)
        pool = pool_for(user)
        progress = db.get_progress_map(user_id)
        if request.query.get("early") == "1":
            nearest = learning.earliest_due(pool, progress)
            sign_id, mode = (nearest["sign_id"], "review") if nearest else (None, None)
        else:
            sign_id, mode = learning.pick_next(pool, progress)
        if mode == "review":
            options = learning.build_quiz_options(sign_id, signs_main, get_valid(), user["study_language"])
            return no_store({"mode": "review", "sign_id": sign_id, "options": options,
                             "box": progress[sign_id]["box"] if sign_id in progress else 0})
        if mode == "new":
            return no_store({"mode": "new", "sign_id": sign_id})
        nearest = learning.earliest_due(pool, progress)
        return no_store({"mode": "done", "queued": sum(1 for s in pool if s in progress),
                         "next_in": max(0, nearest["next_review_at"] - int(time.time())) if nearest else None})

    async def study_seen(request: web.Request):
        user_id = user_id_from(request)
        registered_user(user_id)
        require_premium(user_id)
        sign_id = valid_sign((await body(request)).get("sign_id"))
        box, next_review = learning.schedule_after_intro(int(time.time()))
        db.introduce_sign(user_id, sign_id, box, next_review)
        return no_store({"ok": True})

    async def study_known(request: web.Request):
        user_id = user_id_from(request)
        registered_user(user_id)
        require_premium(user_id)
        sign_id = valid_sign((await body(request)).get("sign_id"))
        box, next_review = learning.schedule_known(int(time.time()))
        db.set_box(user_id, sign_id, box, next_review)
        return no_store({"ok": True, "box": box})

    async def study_answer(request: web.Request):
        user_id = user_id_from(request)
        registered_user(user_id)
        require_premium(user_id)
        data = await body(request)
        sign_id, chosen = valid_sign(data.get("sign_id")), valid_sign(data.get("chosen"))
        now = int(time.time())
        progress = db.get_progress(user_id, sign_id)
        if progress is None:
            box, next_review = learning.schedule_after_intro(now)
            db.introduce_sign(user_id, sign_id, box, next_review)
            progress = db.get_progress(user_id, sign_id)
        correct = chosen == sign_id
        new_box, next_review = learning.schedule_after_answer(progress["box"], correct, now)
        db.record_answer(user_id, sign_id, correct, new_box, next_review)
        return no_store({
            "correct": correct, "correct_id": sign_id, "box": new_box, "max_box": learning.MAX_BOX,
            "mastered_now": correct and new_box >= learning.MASTERED_BOX > progress["box"],
            "next_in": next_review - now,
        })

    # ------------------------------------------------------------ tests

    async def exam_start(request: web.Request):
        user_id = user_id_from(request)
        user = registered_user(user_id)
        require_premium(user_id)
        size = (await body(request)).get("size")
        if size not in EXAM_SIZES or isinstance(size, bool):
            raise web.HTTPBadRequest(text=f"size must be one of {EXAM_SIZES}")
        valid = get_valid()
        lang = user["study_language"]
        picked = random.sample(valid, min(size, len(valid)))
        questions = [{"sign": s, "options": learning.build_quiz_options(s, signs_main, valid, lang)}
                     for s in picked]
        exam_id = secrets.token_urlsafe(16)
        db.create_exam(exam_id, user_id, json.dumps(questions), len(questions))
        return no_store({
            "exam_id": exam_id,
            "seconds": len(questions) * EXAM_SECONDS_PER_QUESTION,
            "pass_ratio": EXAM_PASS_RATIO,
            "questions": [{
                "n": i,
                "image": f"/api/exam/{exam_id}/{i}.webp",
                "scale": sign_scale(q["sign"]),
                "options": [signs_main[o]["names"].get(lang, o) for o in q["options"]],
            } for i, q in enumerate(questions)],
        })

    async def exam_image(request: web.Request):
        exam_id, n = request.match_info["exam_id"], request.match_info["n"]
        if not EXAM_ID.fullmatch(exam_id) or not n.isdigit():
            raise web.HTTPNotFound()
        exam = db.get_exam(exam_id)
        questions = json.loads(exam["questions"]) if exam else []
        if int(n) >= len(questions):
            raise web.HTTPNotFound()
        path = CUTOUTS / f"{questions[int(n)]['sign']}.webp"
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})

    async def exam_finish(request: web.Request):
        user_id = user_id_from(request)
        user = registered_user(user_id)
        data = await body(request)
        exam_id, answers = data.get("exam_id"), data.get("answers")
        exam = db.get_exam(exam_id) if isinstance(exam_id, str) and EXAM_ID.fullmatch(exam_id) else None
        if exam is None or exam["user_id"] != user_id:
            raise web.HTTPNotFound(text="no such test")
        questions = json.loads(exam["questions"])
        if not isinstance(answers, list) or len(answers) != len(questions) or not all(
                a is None or (isinstance(a, int) and not isinstance(a, bool) and 0 <= a < 4)
                for a in answers):
            raise web.HTTPBadRequest(text="one answer index (0-3) or null per question")
        lang = user["study_language"]

        def name(sign_id: str) -> str:
            return signs_main[sign_id]["names"].get(lang, sign_id)

        items, correct = [], 0
        for q, a in zip(questions, answers):
            chosen = q["options"][a] if a is not None and a < len(q["options"]) else None
            ok = chosen == q["sign"]
            correct += ok
            items.append({"sign_id": q["sign"], "ok": ok, "correct": name(q["sign"]),
                          "chosen": name(chosen) if chosen else None})
        if not db.finish_exam(exam_id, json.dumps(answers), correct):
            raise json_error(web.HTTPConflict, "already_finished")
        total = len(questions)
        took = int(time.time()) - exam["created_at"]
        passed = correct >= total * EXAM_PASS_RATIO
        result = {"correct": correct, "total": total, "passed": passed,
                  "timed_out": took > total * EXAM_SECONDS_PER_QUESTION + 30, "items": items}
        if bot is not None:
            try:
                verdict = "складено" if passed else "не складено"
                await bot.send_message(user_id, f"Тест на знаки: {correct} з {total}, {verdict}.")
            except Exception as exc:  # the result is saved; the chat message is a bonus
                logger.info("Mini App: test result not sent to chat (%s)", exc)
        return no_store(result)

    # ------------------------------------------------------------ premium

    async def premium_invoice(request: web.Request):
        user_id = user_id_from(request)
        registered_user(user_id)
        st = premium.status(db, user_id)
        if not st["paywall"] or st["active"]:
            raise json_error(web.HTTPConflict, "not_needed")
        if bot is None:
            raise web.HTTPServiceUnavailable(text="payments are not configured")
        return no_store({"link": await premium.invoice_link(bot, user_id)})

    app.router.add_get("/", index)
    app.router.add_get("/app.css", stylesheet)
    app.router.add_get("/signs/{size:(thumb/)?}{sign_id}.webp", sign_image)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/study/next", study_next)
    app.router.add_post("/api/study/seen", study_seen)
    app.router.add_post("/api/study/known", study_known)
    app.router.add_post("/api/study/answer", study_answer)
    app.router.add_post("/api/exam/start", exam_start)
    app.router.add_get("/api/exam/{exam_id}/{n}.webp", exam_image)
    app.router.add_post("/api/exam/finish", exam_finish)
    app.router.add_post("/api/premium/invoice", premium_invoice)
    app.router.add_static("/dist", WEBAPP / "dist")
    app.router.add_static("/_kit", WEBAPP / "_kit")
    return app


async def start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host=os.getenv("WEBAPP_HOST", "0.0.0.0"), port=port).start()
    logger.info("Mini App server on port %s", port)
    return runner
