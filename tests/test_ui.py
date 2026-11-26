import ast
import inspect
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from aiogram.types import InputRichBlockTable, InlineKeyboardButton, Message
from aiogram.methods import EditMessageText, SendRichMessage

os.environ.setdefault(
    "BOT_TOKEN",
    "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
)

import bot as app
from keyboards import (
    BTN_CATEGORIES,
    BTN_SETTINGS,
    BTN_STATS,
    BTN_STUDY,
    get_categories_keyboard,
    get_delete_confirm_keyboard,
    get_details_keyboard,
    get_home_keyboard,
    get_mydata_keyboard,
    get_theory_keyboard,
    get_early_review_keyboard,
    get_feedback_keyboard,
    get_intro_keyboard,
    get_language_keyboard,
    get_main_menu_keyboard,
    get_quiz_keyboard,
    get_reset_confirm_keyboard,
    get_settings_keyboard,
    get_theme_keyboard,
    get_translation_keyboard,
)
from utils import MAX_SIGN_CANVAS_SIZE, process_sign_image


ACTION_FIELDS = {
    "url",
    "callback_data",
    "web_app",
    "login_url",
    "switch_inline_query",
    "switch_inline_query_current_chat",
    "switch_inline_query_chosen_chat",
    "copy_text",
    "callback_game",
    "pay",
}


def inline_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.signs = {
            "100": {
                "names": {"no": "Fare", "en": "Danger"},
                "category": {"names": {"no": "Fareskilt", "en": "Warning signs"}},
                "category_code": "warning",
            },
            "200": {
                "names": {"no": "Stopp", "en": "Stop"},
                "category": {"names": {"no": "Fareskilt", "en": "Warning signs"}},
                "category_code": "warning",
            },
        }

    def all_inline_markups(self):
        return [
            get_language_keyboard(include_back=True, current_language="no"),
            get_translation_keyboard(current_language="uk"),
            get_intro_keyboard("100"),
            get_quiz_keyboard("100", ["100", "200"], self.signs, "no"),
            get_feedback_keyboard("100"),
            get_details_keyboard(),
            get_early_review_keyboard(),
            get_settings_keyboard(),
            get_theme_keyboard("dark"),
            get_reset_confirm_keyboard(),
            get_categories_keyboard(self.signs, "no", "warning", ["100", "200"]),
            get_home_keyboard(3),
            get_theory_keyboard(),
            get_mydata_keyboard(),
            get_delete_confirm_keyboard(),
        ]

    def test_home_keyboard_opens_the_app_when_configured(self):
        markup = get_home_keyboard(0, "https://example.test/app")
        web_apps = [b for b in inline_buttons(markup) if b.web_app]
        self.assertEqual(len(web_apps), 1)
        self.assertEqual(web_apps[0].web_app.url, "https://example.test/app")
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "study_next")
        self.assertEqual(markup.inline_keyboard[0][0].style, "primary")

    def test_main_menu_is_persistent_and_never_requires_typing(self):
        markup = get_main_menu_keyboard()
        labels = [button.text for row in markup.keyboard for button in row]

        self.assertTrue(markup.resize_keyboard)
        self.assertFalse(markup.is_persistent)
        self.assertTrue(markup.one_time_keyboard)            # hides while the user learns
        self.assertLessEqual(len(markup.input_field_placeholder), 64)
        self.assertEqual(markup.keyboard[0][0].style, "primary")
        self.assertEqual(
            labels,
            [BTN_STUDY, BTN_STATS, BTN_CATEGORIES, BTN_SETTINGS],
        )

    def test_inline_buttons_have_one_action_and_short_callbacks(self):
        allowed_styles = {None, "primary", "success", "danger"}
        for markup in self.all_inline_markups():
            labels = []
            primary_count = 0
            for button in inline_buttons(markup):
                payload = button.model_dump(exclude_none=True)
                actions = ACTION_FIELDS.intersection(payload)
                self.assertEqual(actions, {"callback_data"}, payload)
                self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)
                self.assertIn(button.style, allowed_styles)
                if button.style == "danger":
                    self.assertIn(button.callback_data, {"reset_confirm", "data_delete_confirm"})
                primary_count += button.style == "primary"
                labels.append(button.text)
            self.assertEqual(len(labels), len(set(labels)), labels)
            self.assertLessEqual(primary_count, 1)

    def test_existing_callback_payloads_are_preserved(self):
        callbacks = {
            button.callback_data
            for markup in self.all_inline_markups()
            for button in inline_buttons(markup)
        }
        legacy_callbacks = {
            "lang_no",
            "lang_en",
            "trans_none",
            "trans_no",
            "trans_en",
            "trans_uk",
            "trans_ru",
            "study_next",
            "know|100",
            "more|100",
            "q|100|100",
            "q|100|200",
            "study_early",
            "change_language",
            "change_theme",
            "reset_progress",
            "theme_light",
            "theme_dark",
            "settings_back",
            "reset_confirm",
            "cat_all",
            "cat_warning",
            "cat_done",
        }
        self.assertTrue(legacy_callbacks.issubset(callbacks))

    def test_destructive_confirmation_is_isolated(self):
        markup = get_reset_confirm_keyboard()
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1, 1])
        self.assertIn("прогрес", markup.inline_keyboard[0][0].text.lower())
        self.assertIn("залишити", markup.inline_keyboard[1][0].text.lower())
        self.assertEqual(markup.inline_keyboard[0][0].style, "danger")
        self.assertIsNone(markup.inline_keyboard[1][0].style)

    def test_theme_keyboard_reflects_current_state(self):
        markup = get_theme_keyboard("dark")
        self.assertEqual(markup.inline_keyboard[0][0].text, "Світла")
        self.assertEqual(markup.inline_keyboard[0][1].text, "✅ Темна")   # icon 'selected', Unicode fallback
        self.assertIsNone(markup.inline_keyboard[0][0].style)
        self.assertEqual(markup.inline_keyboard[0][1].style, "success")

    def test_language_keyboards_mark_current_values(self):
        study = get_language_keyboard(current_language="no")
        translation = get_translation_keyboard(current_language="uk")

        self.assertTrue(study.inline_keyboard[0][0].text.startswith("✅ "))
        self.assertEqual(study.inline_keyboard[0][0].style, "success")
        uk_button = next(
            button for button in inline_buttons(translation)
            if button.callback_data == "trans_uk"
        )
        self.assertTrue(uk_button.text.startswith("✅ "))
        self.assertEqual(uk_button.style, "success")

    def test_sdk_exposes_rich_messages_and_button_styles(self):
        self.assertIn("style", InlineKeyboardButton.model_fields)
        self.assertTrue(hasattr(Message, "answer_rich"))
        self.assertIn("rich_message", inspect.signature(Message.answer_rich).parameters)
        self.assertIn("rich_message", SendRichMessage.model_fields)
        self.assertIn("rich_message", EditMessageText.model_fields)


class MessageTests(unittest.TestCase):
    def stats_kwargs(self, *, answered=20):
        return {
            "mastered": 12,
            "total": 100,
            "in_learning": 8,
            "new": 80,
            "due_now": 3,
            "answered": answered,
            "correct_total": 15 if answered else 0,
            "today_answered": 4 if answered else 0,
            "today_correct": 3 if answered else 0,
            "streak": 2 if answered else 0,
            "category_rows": [("Попереджувальні <&>", 3, 10), ("Сервіс", 10, 10)],
        }

    def test_statistics_use_three_native_bordered_tables(self):
        rich_message = app.build_statistics_rich_message(**self.stats_kwargs())
        tables = [
            block for block in rich_message.blocks
            if isinstance(block, InputRichBlockTable)
        ]

        self.assertEqual(len(tables), 3)
        self.assertEqual([table.caption for table in tables], [
            "Знаки", "Результати", "За категоріями",
        ])
        for table in tables:
            self.assertTrue(table.is_bordered)
            self.assertTrue(table.is_striped)
            self.assertTrue(all(cell.is_header for cell in table.cells[0]))
            self.assertEqual(table.cells[0][1].align, "right")

        self.assertEqual(tables[2].cells[1][0].text, "Попереджувальні <&>")
        self.assertEqual(tables[2].cells[1][1].text, "3/10 · 30%")
        payload = rich_message.model_dump(mode="json", exclude_none=True)
        self.assertEqual(set(payload), {"blocks"})
        table_payloads = [block for block in payload["blocks"] if block["type"] == "table"]
        self.assertEqual(len(table_payloads), 3)
        self.assertIn("cells", table_payloads[0])
        self.assertNotIn("rows", table_payloads[0])

    def test_statistics_empty_state_and_html_fallback(self):
        kwargs = self.stats_kwargs(answered=0)
        rich_message = app.build_statistics_rich_message(**kwargs)
        fallback = app.build_statistics_text(**kwargs)

        self.assertIn("Ще немає відповідей", rich_message.blocks[-2].text)
        buttons = rich_message.blocks[-1].buttons                 # embedded rich buttons close the message
        self.assertEqual(buttons[0].callback_data, "study_next")
        self.assertEqual(buttons[0].style, "primary")
        self.assertIn("Точність: —", fallback)
        self.assertIn("Попереджувальні &lt;&amp;&gt;", fallback)
        self.assertNotIn("Попереджувальні <&>", fallback)

    def test_settings_table_contains_only_editable_values(self):
        user = {
            "study_language": "no",
            "translation_language": "uk",
            "theme": "dark",
        }
        rich_message = app.build_settings_rich_message(user)
        table = next(
            block for block in rich_message.blocks
            if isinstance(block, InputRichBlockTable)
        )
        rows = [(row[0].text, row[1].text) for row in table.cells[1:]]

        self.assertEqual(rows, [
            ("Мова знаків", "Норвезька"),
            ("Переклад", "Українська"),
            ("Тема карток", "Темна"),
        ])
        self.assertNotIn("Вивчено", app.build_settings_text(user))

    def test_new_sign_heading_is_not_repeated(self):
        for sign_id in app.signs_main:
            for study_lang in ("no", "en"):
                for trans_lang in ("none", "no", "en", "ru", "uk"):
                    text = app.intro_card_text(sign_id, study_lang, trans_lang)
                    self.assertNotIn("🆕", text)
                    self.assertNotIn("Новий знак", text)
                    self.assertLessEqual(app.html_visible_length(text), app.CAPTION_LIMIT)

    def test_dynamic_sign_text_is_html_escaped(self):
        unsafe_sign = {
            "names": {"no": "<b>Falsk</b> & tegn", "uk": "<script>"},
            "descriptions": {"no": "5 < 7 & 8 > 6", "uk": "<i>tekst</i>"},
            "category": {"names": {"no": "A&B"}},
        }
        with patch.dict(app.signs_main, {"unsafe": unsafe_sign}):
            text = app.intro_card_text("unsafe", "no", "uk")

        self.assertIn("&lt;b&gt;Falsk&lt;/b&gt; &amp; tegn", text)
        self.assertIn("5 &lt; 7 &amp; 8 &gt; 6", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("<i>tekst</i>", text)

    def test_only_html_parse_mode_is_used(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        self.assertNotIn('parse_mode="Markdown"', source)
        self.assertNotIn("parse_mode='Markdown'", source)

    def test_command_menu_covers_every_main_section(self):
        commands = {item.command for item in app.BOT_COMMANDS}
        self.assertEqual(
            commands,
            {"start", "learn", "stats", "categories", "settings", "reset",
             "premium", "paysupport", "theory"},
        )

    def test_every_callback_handler_answers_telegram(self):
        source = Path(app.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        callback_handlers = []

        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            is_callback_handler = any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "callback_query"
                for decorator in node.decorator_list
            )
            if not is_callback_handler:
                continue
            callback_handlers.append(node.name)
            answers_callback = any(
                isinstance(child, ast.Await)
                and isinstance(child.value, ast.Call)
                and isinstance(child.value.func, ast.Attribute)
                and child.value.func.attr == "answer"
                and isinstance(child.value.func.value, ast.Name)
                and child.value.func.value.id == "callback"
                for child in ast.walk(node)
            )
            self.assertTrue(answers_callback, node.name)

        self.assertGreaterEqual(len(callback_handlers), 10)


class MediaTests(unittest.TestCase):
    def test_large_production_image_fits_telegram_photo_limits(self):
        image_path = Path(app.__file__).parent / "data" / "images" / "940_0.jpg"
        output = process_sign_image(str(image_path), theme="light")

        self.assertIsNotNone(output)
        self.assertLess(output.getbuffer().nbytes, 10 * 1024 * 1024)
        with Image.open(output) as image:
            width, height = image.size

        self.assertLessEqual(width, MAX_SIGN_CANVAS_SIZE)
        self.assertLessEqual(height, MAX_SIGN_CANVAS_SIZE)
        self.assertLessEqual(width + height, 10_000)
        self.assertLessEqual(max(width, height) / min(width, height), 20)


class SignLibraryTests(unittest.TestCase):
    def test_every_listed_sign_uses_a_cutout(self):
        from utils import find_sign_image, load_signs_list

        missing = [s for s in load_signs_list()
                   if not (find_sign_image(s) or "").endswith(".webp")]
        # Three records have no artwork at all yet (see docs/audit/data-audit.md).
        self.assertLessEqual(set(missing), {"146_0", "516_0", "521_2"})

    def test_cutout_background_is_transparent(self):
        from utils import find_sign_image

        with Image.open(find_sign_image("100_1")) as triangle:
            self.assertEqual(triangle.mode, "RGBA")
            self.assertEqual(triangle.getpixel((0, 0))[3], 0)
            w, h = triangle.size
            self.assertEqual(triangle.getpixel((w // 2, h // 2))[3], 255)

    def test_dark_card_has_no_white_paper_around_the_sign(self):
        from utils import find_sign_image

        output = process_sign_image(find_sign_image("302_0"), theme="dark")
        with Image.open(output) as card:
            corner = card.convert("RGB").getpixel((5, 5))
        self.assertTrue(all(c < 80 for c in corner), corner)


class HomeAndDataTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from database import Database
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, "h.db"))
        self.db.init_db()
        self.db.upsert_user(9, "no", "uk")
        self.db.touch_identity(9, first_name="<b>Ola</b>", last_name=None, username="ola",
                               language_code="uk", is_premium=False)
        self.db.update_profile(9, {"exam_date": "2099-01-01", "licence_class": "A1"})
        self.patches = [patch.object(app, "db", self.db), patch.object(app, "VALID_SIGNS", ["100_1", "302_0"])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_home_screen_shows_progress_goal_and_one_forward_action(self):
        text, kb = app.home_screen(self.db.get_user(9), "<b>Ola</b>")
        self.assertIn("&lt;b&gt;Ola&lt;/b&gt;", text)     # names are escaped
        self.assertIn("категорія A1", text)
        self.assertIn("іспит через", text)
        self.assertIn("Вивчено 0 знаків з 2", text)
        self.assertNotIn("▰", text)                       # no ASCII progress bar any more
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "study_next")

    def test_mydata_lists_the_record_and_delete_removes_it(self):
        text = app.mydata_text(self.db.get_user(9))
        self.assertIn("@ola", text)
        self.assertIn("A1", text)
        self.assertNotIn("<b>Ola</b>", text)
        self.db.delete_user_data(9)
        self.assertIsNone(self.db.get_user(9))

    def test_theory_screen_follows_the_licence_class(self):
        self.assertIn("Мопед", app.theory_screen_text("AM146"))
        self.assertNotIn("Мопед", app.theory_screen_text("B"))


if __name__ == "__main__":
    unittest.main()
