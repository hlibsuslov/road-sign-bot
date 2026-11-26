"""Keyboards. Every icon comes from icons.py: one premium emoji family when the owner turned
it on (CUSTOM_EMOJI=1), the same meanings in Unicode otherwise. callback_data never changes."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

import icons

# Reply-keyboard labels. Handlers accept both spellings: with a premium icon the text has
# no emoji of its own, and old keyboards in users' chats still send the Unicode version.
STUDY_TEXT, STATS_TEXT, CATEGORIES_TEXT, SETTINGS_TEXT = "Вчитися", "Статистика", "Категорії", "Налаштування"
BTN_STUDY = f"{icons.char('study')} {STUDY_TEXT}"
BTN_STATS = f"{icons.char('stats')} {STATS_TEXT}"
BTN_CATEGORIES = f"{icons.char('categories')} {CATEGORIES_TEXT}"
BTN_SETTINGS = f"{icons.char('settings')} {SETTINGS_TEXT}"
REPLY_TEXTS = {
    "study": {BTN_STUDY, STUDY_TEXT},
    "stats": {BTN_STATS, STATS_TEXT},
    "categories": {BTN_CATEGORIES, CATEGORIES_TEXT},
    "settings": {BTN_SETTINGS, SETTINGS_TEXT},
}
BACK_TEXT = "Назад"

MAX_OPTION_LEN = 48


def button(slot: str | None, text: str, **kwargs) -> InlineKeyboardButton:
    """Inline button with the slot's icon (premium or Unicode)."""
    if slot is None:
        return InlineKeyboardButton(text=text, **kwargs)
    label, cid = icons.label(slot, text)
    if cid:
        kwargs["icon_custom_emoji_id"] = cid
    return InlineKeyboardButton(text=label, **kwargs)


def back(callback_data: str, text: str = BACK_TEXT) -> InlineKeyboardButton:
    return button("back", text, callback_data=callback_data)


def _choice(selected: bool, text: str, **kwargs) -> InlineKeyboardButton:
    """A choice in a list: the selected one carries the 'selected' icon and the success colour."""
    if selected:
        return button("selected", text, style="success", **kwargs)
    return InlineKeyboardButton(text=text, **kwargs)


def _reply(slot: str, text: str, **kwargs) -> KeyboardButton:
    label, cid = icons.label(slot, text)
    return KeyboardButton(text=label, icon_custom_emoji_id=cid, **kwargs) if cid else KeyboardButton(text=label, **kwargs)


def get_language_keyboard(include_back: bool = False,
                          current_language: str | None = None) -> InlineKeyboardMarkup:
    options = [
        ("no", "🇳🇴 Норвезька (Norsk)"),
        ("en", "🇬🇧 Англійська (English)"),
    ]
    keyboard = [[_choice(code == current_language, label, callback_data=f"lang_{code}")] for code, label in options]
    if include_back:
        keyboard.append([back("settings_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_translation_keyboard(current_language: str | None = None) -> InlineKeyboardMarkup:
    def option(code: str, label: str) -> InlineKeyboardButton:
        return _choice(code == current_language, label, callback_data=f"trans_{code}")

    keyboard = [
        [option("none", "Без перекладу")],
        [option("no", "🇳🇴 Норвезька"), option("en", "🇬🇧 Англійська")],
        [option("uk", "🇺🇦 Українська"), option("ru", "🇷🇺 Російська")],
        [back("lang_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [_reply("study", STUDY_TEXT, style="primary")],
        [_reply("stats", STATS_TEXT), _reply("categories", CATEGORIES_TEXT)],
        [_reply("settings", SETTINGS_TEXT)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Оберіть дію",
    )


def get_intro_keyboard(sign_id: str) -> InlineKeyboardMarkup:
    """Картка знайомства з новим знаком."""
    keyboard = [
        [button("next", "Далі", callback_data="study_next", style="primary")],
        [button("known", "Я вже знаю", callback_data=f"know|{sign_id}"),
         button("info", "Пояснення", callback_data=f"more|{sign_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_OPTION_LEN else text[:MAX_OPTION_LEN - 1] + "…"


def get_quiz_keyboard(sign_id: str, options: list, signs_main: dict, study_lang: str) -> InlineKeyboardMarkup:
    """Варіанти відповіді квізу: по одному в рядку, без іконок — тут важливий лише текст."""
    keyboard = []
    for opt_id in options:
        name = signs_main[opt_id]["names"].get(study_lang, opt_id)
        keyboard.append([InlineKeyboardButton(text=_truncate(name), callback_data=f"q|{sign_id}|{opt_id}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_feedback_keyboard(sign_id: str) -> InlineKeyboardMarkup:
    """Після відповіді у квізі."""
    keyboard = [
        [button("next", "Далі", callback_data="study_next", style="primary"),
         button("info", "Пояснення", callback_data=f"more|{sign_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_details_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("study", "Продовжити навчання", callback_data="study_next", style="primary")],
    ])


def get_early_review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("repeat", "Повторити зараз", callback_data="study_early", style="primary")],
    ])


def get_settings_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [button("language", "Мови", callback_data="change_language"),
         button("theme", "Тема карток", callback_data="change_theme")],
        [button("premium", "Преміум", callback_data="premium_open")],
        [button("data", "Мої дані", callback_data="data_show")],
        [InlineKeyboardButton(text="Скинути весь прогрес", callback_data="reset_progress")],
        [button("home", "Головна", callback_data="home_open")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_theme_keyboard(current_theme: str = "light") -> InlineKeyboardMarkup:
    keyboard = [
        [_choice(current_theme == "light", "Світла", callback_data="theme_light"),
         _choice(current_theme == "dark", "Темна", callback_data="theme_dark")],
        [back("settings_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_reset_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Скинути весь прогрес", callback_data="reset_confirm", style="danger")],
        [back("settings_back", "Залишити прогрес")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_categories_keyboard(signs_main_data: dict, study_lang: str,
                            current_cats_str: str = 'all',
                            valid_sign_ids: list = None) -> InlineKeyboardMarkup:
    categories_info = {}  # code -> {name, count}, тільки знаки з картинками
    valid_set = set(valid_sign_ids) if valid_sign_ids else None
    for sign_id, data in signs_main_data.items():
        if valid_set is not None and sign_id not in valid_set:
            continue
        if "category" in data and "category_code" in data:
            code = data["category_code"]
            name = data["category"]["names"].get(study_lang, code) if "names" in data["category"] else code
            categories_info.setdefault(code, {"name": name, "count": 0})
            categories_info[code]["count"] += 1

    current_list = current_cats_str.split(',') if current_cats_str != 'all' else ['all']
    total_signs = sum(c['count'] for c in categories_info.values())

    def row(selected: bool, text: str, callback_data: str) -> list:
        slot = "selected" if selected else "unselected"
        return [button(slot, text, callback_data=callback_data)]

    keyboard = [row('all' in current_list, f"Усі категорії · {total_signs}", "cat_all")]
    for code, info in sorted(categories_info.items(), key=lambda x: x[1]['name']):
        keyboard.append(row(code in current_list, f"{info['name']} · {info['count']}", f"cat_{code}"))
    keyboard.append([button("done", "Готово", callback_data="cat_done", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_home_keyboard(due: int, webapp_url: str | None = None) -> InlineKeyboardMarkup:
    """Головний екран: одна дія вперед (primary), розділи — поруч."""
    study = f"Вчитися · {due} до повторення" if due else "Вчитися"
    rows = [[button("study", study, callback_data="study_next", style="primary")]]
    if webapp_url:
        rows.append([button("theory", "Теорія і тести", web_app=WebAppInfo(url=webapp_url))])
    else:
        rows.append([button("theory", "Теорія і тести", callback_data="home_theory")])
    rows.append([button("stats", "Прогрес", callback_data="home_stats"),
                 button("categories", "Категорії", callback_data="home_categories")])
    rows.append([button("settings", "Налаштування", callback_data="home_settings"),
                 button("premium", "Преміум", callback_data="premium_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("study", "Вчитися", callback_data="study_next", style="primary")],
        [button("info", "Таблиця детально", callback_data="stats_details"),
         button("home", "Головна", callback_data="home_open")],
    ])


def get_theory_keyboard(webapp_url: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if webapp_url:
        rows.append([button("app", "Відкрити застосунок", web_app=WebAppInfo(url=webapp_url), style="primary")])
    rows.append([button("study", "Вчити знаки", callback_data="study_next")])
    rows.append([button("home", "Головна", callback_data="home_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_mydata_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("trash", "Видалити мої дані", callback_data="data_delete")],
        [back("settings_back")],
    ])


def get_delete_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Видалити всі мої дані", callback_data="data_delete_confirm", style="danger")],
        [back("settings_back", "Залишити дані")],
    ])
