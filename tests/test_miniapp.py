import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import urllib.parse

from aiohttp.test_utils import AioHTTPTestCase

import learning
import miniapp_server
from database import Database
from utils import load_signs_extra, load_signs_list, load_signs_main

TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


def signed_init_data(user_id: int, *, token: str = TOKEN, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAEtest",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


class MiniAppServerTests(AioHTTPTestCase):
    async def get_application(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # database.py leaves connections open
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        self.db.init_db()
        self.db.upsert_user(42, "no", "uk")
        now = int(time.time())
        self.db.set_box(42, "100_1", learning.MASTERED_BOX, now + 86400)
        self.db.introduce_sign(42, "302_0", 0, now - 10)
        catalog = miniapp_server.build_catalog(load_signs_main(), load_signs_extra(), load_signs_list())
        return miniapp_server.create_app(db=self.db, bot_token=TOKEN, get_catalog=lambda: catalog)

    async def tearDownAsync(self):
        self.tmp.cleanup()

    async def test_catalog_is_public_and_complete(self):
        resp = await self.client.get("/api/catalog")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        ids = {s["id"] for s in data["signs"]}
        self.assertIn("100_1", ids)
        self.assertIn("902_0H", ids)  # was hidden by the letter-O typo
        self.assertEqual(sum(c["count"] for c in data["categories"]), len(data["signs"]))

    async def test_sign_image_and_path_guard(self):
        resp = await self.client.get("/signs/100_1.webp")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.content_type, "image/webp")
        for bad in ("/signs/..%2Fbot.webp", "/signs/999_9.webp", "/signs/100_1%00.webp"):
            self.assertEqual((await self.client.get(bad)).status, 404, bad)

    async def test_me_requires_valid_init_data(self):
        self.assertEqual((await self.client.get("/api/me")).status, 401)
        forged = signed_init_data(42, token="987654321:ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvutsrqp")
        resp = await self.client.get("/api/me", headers={"Authorization": f"tma {forged}"})
        self.assertEqual(resp.status, 401)
        stale = signed_init_data(42, auth_date=int(time.time()) - 3 * 86400)
        resp = await self.client.get("/api/me", headers={"Authorization": f"tma {stale}"})
        self.assertEqual(resp.status, 401)
        tampered = signed_init_data(42).replace("%22id%22%3A42", "%22id%22%3A43")
        resp = await self.client.get("/api/me", headers={"Authorization": f"tma {tampered}"})
        self.assertEqual(resp.status, 401)

    async def test_me_returns_only_the_callers_progress(self):
        resp = await self.client.get("/api/me", headers={"Authorization": f"tma {signed_init_data(42)}"})
        self.assertEqual(resp.status, 200)
        me = await resp.json()
        self.assertTrue(me["registered"])
        self.assertEqual(me["study_language"], "no")
        self.assertEqual(me["progress"]["100_1"]["box"], learning.MASTERED_BOX)
        self.assertTrue(me["progress"]["302_0"]["due"])

        other = await self.client.get("/api/me", headers={"Authorization": f"tma {signed_init_data(7)}"})
        self.assertEqual(await other.json(), {"registered": False})


if __name__ == "__main__":
    unittest.main()
