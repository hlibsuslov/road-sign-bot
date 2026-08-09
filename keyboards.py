from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

BTN_STUDY = "🎓 Вчитися"
BTN_STATS = "📊 Статистика"
BTN_CATEGORIES = "📂 Категорії"
BTN_SETTINGS = "⚙️ Налаштування"
BTN_BACK = "← Назад"

MAX_OPTION_LEN = 48


def get_language_keyboard(include_back: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🇳🇴 Норвезька (Norsk)", callback_data="lang_no")],
        [InlineKeyboardButton(text="🇬🇧 Англійська (English)", callback_data="lang_en")],
    ]
    if include_back:
        keyboard.append([InlineKeyboardButton(text=BTN_BACK, callback_data="settings_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_translation_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🚫 Без перекладу", callback_data="trans_none")],
        [InlineKeyboardButton(text="🇳🇴 Норвезька", callback_data="trans_no"),
         InlineKeyboardButton(text="🇬🇧 Англійська", callback_data="trans_en")],
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="trans_uk"),
         InlineKeyboardButton(text="🇷🇺 Російська", callback_data="trans_ru")],
        [InlineKeyboardButton(text=BTN_BACK, callback_data="lang_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=BTN_STUDY)],
        [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_CATEGORIES)],
        [KeyboardButton(text=BTN_SETTINGS)],
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
        [InlineKeyboardButton(text="Далі", callback_data="study_next")],
        [InlineKeyboardButton(text="Я вже знаю", callback_data=f"know|{sign_id}"),
         InlineKeyboardButton(text="Пояснення", callback_data=f"more|{sign_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_OPTION_LEN else text[:MAX_OPTION_LEN - 1] + "…"


def get_quiz_keyboard(sign_id: str, options: list, signs_main: dict, study_lang: str) -> InlineKeyboardMarkup:
    """Варіанти відповіді квізу: по одному в рядку."""
    keyboard = []
    for opt_id in options:
        name = signs_main[opt_id]["names"].get(study_lang, opt_id)
        keyboard.append([InlineKeyboardButton(
            text=_truncate(name),
            callback_data=f"q|{sign_id}|{opt_id}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_feedback_keyboard(sign_id: str) -> InlineKeyboardMarkup:
    """Після відповіді у квізі."""
    keyboard = [
        [InlineKeyboardButton(text="Далі", callback_data="study_next"),
         InlineKeyboardButton(text="Пояснення", callback_data=f"more|{sign_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_details_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продовжити навчання", callback_data="study_next")],
    ])


def get_early_review_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Повторити зараз", callback_data="study_early")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Змінити мови", callback_data="change_language")],
        [InlineKeyboardButton(text="Змінити тему", callback_data="change_theme")],
        [InlineKeyboardButton(text="Скинути прогрес", callback_data="reset_progress")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_theme_keyboard(current_theme: str = "light") -> InlineKeyboardMarkup:
    light_label = "✓ Світла" if current_theme == "light" else "Світла"
    dark_label = "✓ Темна" if current_theme == "dark" else "Темна"
    keyboard = [
        [InlineKeyboardButton(text=light_label, callback_data="theme_light"),
         InlineKeyboardButton(text=dark_label, callback_data="theme_dark")],
        [InlineKeyboardButton(text=BTN_BACK, callback_data="settings_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_reset_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Скинути весь прогрес", callback_data="reset_confirm")],
        [InlineKeyboardButton(text="Залишити прогрес", callback_data="settings_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_categories_keyboard(signs_main_data: dict, study_lang: str,
                            current_cats_str: str = 'all',
                            valid_sign_ids: list = None) -> InlineKeyboardMarkup:
    # Статистика по категоріях (тільки валідні знаки)
    categories_info = {}  # code -> {name, count}
    valid_set = set(valid_sign_ids) if valid_sign_ids else None

    for sign_id, data in signs_main_data.items():
        if valid_set is not None and sign_id not in valid_set:
            continue
        if "category" in data and "category_code" in data:
            code = data["category_code"]
            name = data["category"]["names"].get(study_lang, code) if "names" in data["category"] else code
            if code not in categories_info:
                categories_info[code] = {"name": name, "count": 0}
            categories_info[code]["count"] += 1

    keyboard = []
    current_list = current_cats_str.split(',') if current_cats_str != 'all' else ['all']
    is_all_selected = 'all' in current_list
    total_signs = sum(c['count'] for c in categories_info.values())

    all_marker = "✓" if is_all_selected else "○"
    keyboard.append([InlineKeyboardButton(
        text=f"{all_marker} Усі категорії · {total_signs}",
        callback_data="cat_all",
    )])

    for code, info in sorted(categories_info.items(), key=lambda x: x[1]['name']):
        marker = "✓" if code in current_list else "○"
        btn_text = f"{marker} {info['name']} · {info['count']}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"cat_{code}")])

    keyboard.append([InlineKeyboardButton(text="Готово", callback_data="cat_done")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
