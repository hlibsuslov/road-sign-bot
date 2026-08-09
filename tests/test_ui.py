import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

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
    get_details_keyboard,
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
            get_language_keyboard(include_back=True),
            get_translation_keyboard(),
            get_intro_keyboard("100"),
            get_quiz_keyboard("100", ["100", "200"], self.signs, "no"),
            get_feedback_keyboard("100"),
            get_details_keyboard(),
            get_early_review_keyboard(),
            get_settings_keyboard(),
            get_theme_keyboard("dark"),
            get_reset_confirm_keyboard(),
            get_categories_keyboard(self.signs, "no", "warning", ["100", "200"]),
        ]

    def test_main_menu_is_persistent_and_never_requires_typing(self):
        markup = get_main_menu_keyboard()
        labels = [button.text for row in markup.keyboard for button in row]

        self.assertTrue(markup.resize_keyboard)
        self.assertTrue(markup.is_persistent)
        self.assertFalse(markup.one_time_keyboard)
        self.assertLessEqual(len(markup.input_field_placeholder), 64)
        self.assertEqual(
            labels,
            [BTN_STUDY, BTN_STATS, BTN_CATEGORIES, BTN_SETTINGS],
        )

    def test_inline_buttons_have_one_action_and_short_callbacks(self):
        for markup in self.all_inline_markups():
            labels = []
            for button in inline_buttons(markup):
                payload = button.model_dump(exclude_none=True)
                actions = ACTION_FIELDS.intersection(payload)
                self.assertEqual(actions, {"callback_data"}, payload)
                self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)
                labels.append(button.text)
            self.assertEqual(len(labels), len(set(labels)), labels)

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

    def test_theme_keyboard_reflects_current_state(self):
        markup = get_theme_keyboard("dark")
        self.assertEqual(markup.inline_keyboard[0][0].text, "Світла")
        self.assertEqual(markup.inline_keyboard[0][1].text, "✓ Темна")


class MessageTests(unittest.TestCase):
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
            {"start", "learn", "stats", "categories", "settings", "reset"},
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


if __name__ == "__main__":
    unittest.main()
