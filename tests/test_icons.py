import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import icons
import keyboards
import progress_card
from database import Database


def sticker(emoji, cid, animated=False):
    return SimpleNamespace(emoji=emoji, custom_emoji_id=cid, is_animated=animated, is_video=False)


class IconTests(unittest.TestCase):
    def tearDown(self):
        icons._state.ids = {}

    def test_slots_resolve_by_meaning_and_prefer_static(self):
        pack = SimpleNamespace(stickers=[
            sticker("⚙", "5258096772776991776"),              # variation selector ignored
            sticker("⬅️", "111", animated=True), sticker("◀️", "222"),
            sticker("✅", "333"),
        ])
        ids = icons.resolve_from_sets([pack])
        self.assertEqual(ids["settings"], "5258096772776991776")
        self.assertEqual(ids["back"], "111")              # first meaning wins over animation order
        self.assertEqual(ids["selected"], "333")
        self.assertNotIn("home", ids)                     # unresolved stays Unicode

    def test_off_by_default_everything_is_unicode(self):
        icons._state.ids = {"settings": "5258096772776991776"}
        with patch.dict(os.environ, {"CUSTOM_EMOJI": "0"}):
            self.assertEqual(icons.tg("settings"), "⚙️")
            self.assertEqual(icons.label("settings", "Налаштування"), ("⚙️ Налаштування", None))

    def test_enabled_buttons_carry_the_icon_and_plain_text(self):
        icons._state.ids = {"back": "222", "selected": "333"}
        with patch.dict(os.environ, {"CUSTOM_EMOJI": "1"}):
            back = keyboards.back("settings_back")
            self.assertEqual(back.text, "Назад")
            self.assertEqual(back.icon_custom_emoji_id, "222")
            self.assertIn('<tg-emoji emoji-id="333">✅</tg-emoji>', icons.tg("selected"))
            menu = keyboards.get_main_menu_keyboard()
            self.assertEqual(menu.keyboard[0][0].text, "🎓 Вчитися")   # 'study' unresolved here
        self.assertIn("Вчитися", keyboards.REPLY_TEXTS["study"])      # handlers accept the plain label


class ProgressCardTests(unittest.TestCase):
    def test_card_renders_for_both_themes(self):
        for theme in ("light", "dark"):
            png = progress_card.render(mastered=10, total=100, categories=[("fareskilt", 5, 48), ("vikeplikt", 7, 7)],
                                       daily=[0, 3, 20], goal=20, theme=theme)
            with Image.open(png) as img:
                self.assertEqual(img.size, (progress_card.W, progress_card.H))

    def test_daily_series_is_oldest_first_with_zeros(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db = Database(os.path.join(tmp.name, "s.db"))
        db.init_db()
        db.upsert_user(1, "no", "uk")
        db.record_theory_answer(1, "vik-001", True)
        series = db.get_daily_series(1, 14)
        self.assertEqual(len(series), 14)
        self.assertEqual(series[-1], 1)
        self.assertEqual(sum(series[:-1]), 0)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
