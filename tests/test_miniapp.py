import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import urllib.parse

from types import SimpleNamespace
from unittest.mock import patch

from aiohttp.test_utils import AioHTTPTestCase

import learning
import miniapp_server
import premium
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
        signs = load_signs_main()
        valid = [s for s in load_signs_list() if s in signs]
        catalog = miniapp_server.build_catalog(signs, load_signs_extra(), valid)
        return miniapp_server.create_app(db=self.db, bot_token=TOKEN, get_catalog=lambda: catalog,
                                         signs_main=signs, get_valid=lambda: valid)

    def auth(self, user_id: int = 42) -> dict:
        return {"Authorization": f"tma {signed_init_data(user_id)}"}

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


    async def test_study_loop_matches_the_chat(self):
        resp = await self.client.get("/api/study/next", headers=self.auth())
        step = await resp.json()
        self.assertEqual(step["mode"], "review")          # 302_0 is overdue: reviews come first
        self.assertEqual(step["sign_id"], "302_0")
        self.assertEqual(len(step["options"]), 4)
        self.assertIn("302_0", step["options"])

        wrong = next(o for o in step["options"] if o != "302_0")
        resp = await self.client.post("/api/study/answer", json={"sign_id": "302_0", "chosen": wrong},
                                      headers=self.auth())
        result = await resp.json()
        self.assertFalse(result["correct"])
        self.assertEqual(result["box"], 0)
        self.assertEqual(self.db.get_progress(42, "302_0")["wrong_count"], 1)

        resp = await self.client.post("/api/study/seen", json={"sign_id": "100_2"}, headers=self.auth())
        self.assertEqual(resp.status, 200)
        self.assertIsNotNone(self.db.get_progress(42, "100_2"))

        bad = await self.client.post("/api/study/answer", json={"sign_id": "302_0", "chosen": "../x"},
                                     headers=self.auth())
        self.assertEqual(bad.status, 400)

    async def test_unregistered_user_gets_a_clear_error(self):
        resp = await self.client.get("/api/study/next", headers=self.auth(7))
        self.assertEqual(resp.status, 409)
        self.assertEqual((await resp.json())["error"], "not_registered")

    async def test_paywall_blocks_study_and_tests_until_paid(self):
        with patch.dict(os.environ, {"PAYWALL_ENABLED": "1"}):
            resp = await self.client.get("/api/study/next", headers=self.auth())
            self.assertEqual(resp.status, 402)
            resp = await self.client.post("/api/exam/start", json={"size": 10}, headers=self.auth())
            self.assertEqual(resp.status, 402)
            me = await (await self.client.get("/api/me", headers=self.auth())).json()
            self.assertFalse(me["premium"]["premium"])

            self.db.upsert_subscription(42, "stxTEST", int(time.time()) + 86400)
            resp = await self.client.get("/api/study/next", headers=self.auth())
            self.assertEqual(resp.status, 200)

    async def test_exam_hides_answers_and_grades_once(self):
        resp = await self.client.post("/api/exam/start", json={"size": 10}, headers=self.auth())
        self.assertEqual(resp.status, 200)
        exam = await resp.json()
        raw = json.dumps(exam)
        stored = json.loads(self.db.get_exam(exam["exam_id"])["questions"])
        for q in stored:
            self.assertNotIn(f'"{q["sign"]}"', raw)        # no sign id leaks to the client
        self.assertEqual(len(exam["questions"]), 10)

        img = await self.client.get(exam["questions"][0]["image"])
        self.assertEqual(img.status, 200)

        answers = [q["options"].index(q["sign"]) for q in stored]
        answers[0] = (answers[0] + 1) % 4
        answers[1] = None
        payload = {"exam_id": exam["exam_id"], "answers": answers}

        other = await self.client.post("/api/exam/finish", json=payload, headers=self.auth(7))
        self.assertIn(other.status, (404, 409))           # someone else's test is invisible

        resp = await self.client.post("/api/exam/finish", json=payload, headers=self.auth())
        result = await resp.json()
        self.assertEqual(result["correct"], 8)
        self.assertFalse(result["passed"])                # 8/10 < 38/45
        self.assertFalse(result["items"][0]["ok"])
        self.assertIsNone(result["items"][1]["chosen"])

        again = await self.client.post("/api/exam/finish", json=payload, headers=self.auth())
        self.assertEqual(again.status, 409)

        bad = await self.client.post("/api/exam/start", json={"size": 999}, headers=self.auth())
        self.assertEqual(bad.status, 400)


class PremiumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, "p.db"))
        self.db.init_db()
        self.db.upsert_user(5, "no", "uk")
        self.env = patch.dict(os.environ, {"PAYWALL_ENABLED": "1", "PREMIUM_STARS": "50"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def payment(self, charge: str, expires: int, *, first=True, payload="premium:5", amount=50):
        return SimpleNamespace(invoice_payload=payload, currency="XTR", total_amount=amount,
                               telegram_payment_charge_id=charge, subscription_expiration_date=expires,
                               is_recurring=True, is_first_recurring=first)

    def test_paywall_off_means_everyone_has_access(self):
        with patch.dict(os.environ, {"PAYWALL_ENABLED": "0"}):
            self.assertTrue(premium.is_premium(self.db, 5))

    def test_pre_checkout_rechecks_everything_on_the_server(self):
        check = premium.check_pre_checkout
        self.assertIsNone(check(self.db, 5, "premium:5", "XTR", 50))
        self.assertIsNotNone(check(self.db, 5, "premium:6", "XTR", 50))   # someone else's invoice
        self.assertIsNotNone(check(self.db, 5, "premium:5", "XTR", 1))    # tampered price
        self.assertIsNotNone(check(self.db, 5, "premium:5", "USD", 50))
        premium.apply_payment(self.db, 5, self.payment("c1", int(time.time()) + 3600))
        self.assertIsNotNone(check(self.db, 5, "premium:5", "XTR", 50))   # no second subscription

    def test_payment_is_applied_once_and_renewals_extend(self):
        now = int(time.time())
        self.assertFalse(premium.is_premium(self.db, 5))
        first = premium.apply_payment(self.db, 5, self.payment("c1", now + 30 * 86400))
        self.assertEqual(first, now + 30 * 86400)
        self.assertTrue(premium.is_premium(self.db, 5))
        self.assertIsNone(premium.apply_payment(self.db, 5, self.payment("c1", now + 30 * 86400)))
        renewal = premium.apply_payment(self.db, 5, self.payment("c2", now + 60 * 86400, first=False))
        self.assertEqual(renewal, now + 60 * 86400)
        self.assertEqual(self.db.get_subscription(5)["charge_id"], "c2")
        self.assertIsNone(premium.apply_payment(self.db, 5, self.payment("c3", now, payload="premium:9")))

    def test_access_ends_after_the_grace_window(self):
        now = int(time.time())
        premium.apply_payment(self.db, 5, self.payment("c1", now - premium.GRACE_SECONDS - 1))
        self.assertFalse(premium.is_premium(self.db, 5))
        premium.apply_payment(self.db, 5, self.payment("c2", now - 60))
        self.assertTrue(premium.is_premium(self.db, 5))                  # a renewal may arrive late


if __name__ == "__main__":
    unittest.main()
