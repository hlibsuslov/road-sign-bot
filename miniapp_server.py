"""HTTP side of the Mini App: static files, sign images and a small JSON API.

Runs in the bot's own event loop (aiohttp ships with aiogram), so the app and the chat
share one SQLite database and one copy of the sign catalogue.

  GET /                      Mini App (webapp/index.html)
  GET /dist/*, /_kit/*       built scripts and the UI kit
  GET /signs/<id>.webp       transparent sign image from data/cutouts
  GET /signs/thumb/<id>.webp 256 px preview for lists
  GET /api/catalog           public: categories and signs (names, texts, shape)
  GET /api/me                private: the caller's settings and progress

Private endpoints trust nothing from the client except initData, checked with the bot
token (HMAC, references/mini-apps/security.md): `Authorization: tma <initData>`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from aiohttp import web

import learning
from init_data import InitDataError, verify_hmac

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent
WEBAPP = BASE / "webapp"
CUTOUTS = BASE / "data" / "cutouts"
SIGN_ID = re.compile(r"[0-9]{3}_[0-9A-Z]{1,4}")
INIT_DATA_MAX_AGE = 24 * 3600   # reading progress; nothing here moves money or rights


def _shapes() -> dict:
    manifest = CUTOUTS / "manifest.json"
    if not manifest.exists():
        return {}
    return {k: v.get("shape") for k, v in json.loads(manifest.read_text("utf-8")).items()}


def build_catalog(signs_main: dict, signs_extra: dict, valid: list[str]) -> dict:
    shapes = _shapes()
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
            "shape": shapes.get(sign_id),
            "names": sign["names"],
            "descriptions": sign["descriptions"],
            "extra": signs_extra.get(sign_id, {}).get("extra", {}),
        })
    return {"categories": sorted(categories.values(), key=lambda c: c["code"]), "signs": signs}


def create_app(*, db, bot_token: str, get_catalog) -> web.Application:
    """get_catalog() returns the catalogue built after the image check at startup."""
    app = web.Application()

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
        }, headers={"Cache-Control": "no-store"})

    app.router.add_get("/", index)
    app.router.add_get("/app.css", stylesheet)
    app.router.add_get("/signs/{size:(thumb/)?}{sign_id}.webp", sign_image)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_get("/api/me", me)
    app.router.add_static("/dist", WEBAPP / "dist")
    app.router.add_static("/_kit", WEBAPP / "_kit")
    return app


async def start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host=os.getenv("WEBAPP_HOST", "0.0.0.0"), port=port).start()
    logger.info("Mini App server on port %s", port)
    return runner
