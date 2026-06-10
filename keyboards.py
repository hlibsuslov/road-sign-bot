from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from utils import load_signs_main

def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🇳🇴 Норвезька мова (Norsk)", callback_data="lang_no"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 Англійська мова (English)", callback_data="lang_en"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_translation_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🚫 Без перекладу", callback_data="trans_none")],
        [InlineKeyboardButton(text="🇳🇴 Норвезька", callback_data="trans_no"), InlineKeyboardButton(text="🇬🇧 Англійська", callback_data="trans_en")],
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="trans_uk"), InlineKeyboardButton(text="🇷🇺 Російська", callback_data="trans_ru")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_card_keyboard(sign_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Вже знаю", callback_data="already_know"),
            InlineKeyboardButton(text="ℹ️ Більше...", callback_data=f"more_{sign_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Нова карточка")],
        [KeyboardButton(text="📂 Категорії")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🌐 Змінити мову", callback_data="change_language"),
        ],
        [
            InlineKeyboardButton(text="🌗 Змінити тему (Світла/Темна)", callback_data="change_theme"),
        ],
        [
            InlineKeyboardButton(text="🔄 Скинути прогрес", callback_data="reset_progress"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_theme_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="☀️ Світла", callback_data="theme_light"),
            InlineKeyboardButton(text="🌑 Темна", callback_data="theme_dark"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="settings_back"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_categories_keyboard(signs_main_data: dict, study_lang: str, current_cats_str: str = 'all', valid_sign_ids: list = None) -> InlineKeyboardMarkup:
    # 1. Збираємо статистику по категоріях
    categories_info = {} # code -> {name: str, count: int}
    
    # Якщо передано список валідних ID, використовуємо його для фільтрації підрахунку
    valid_set = set(valid_sign_ids) if valid_sign_ids else None
    
    for sign_id, data in signs_main_data.items():
        # Рахуємо тільки якщо знак валідний (або якщо перевірка вимкнена)
        if valid_set is not None and sign_id not in valid_set:
            continue
            
        if "category" in data and "category_code" in data:
            code = data["category_code"]
            # Назва категорії залежно від мови вивчення, або дефолтна
            name = data["category"]["names"].get(study_lang, code) if "names" in data["category"] else code
            
            if code not in categories_info:
                categories_info[code] = {"name": name, "count": 0}
            categories_info[code]["count"] += 1
            
    keyboard = []
    
    current_list = current_cats_str.split(',') if current_cats_str != 'all' else ['all']
    is_all_selected = 'all' in current_list
    
    # Підрахунок загальної кількості доступних знаків
    total_signs = sum(c['count'] for c in categories_info.values())
    
    # Кнопка "Всі категорії"
    all_text = f"✅ (Всі) {total_signs} знаків" if is_all_selected else f"Всі категорії ({total_signs})"
    keyboard.append([InlineKeyboardButton(text=f"♾️ {all_text}", callback_data="cat_all")])
    
    # Сортуємо категорії за назвою
    sorted_cats = sorted(categories_info.items(), key=lambda x: x[1]['name'])
    
    # Генеруємо кнопки (в 1 стовпчик для читабельності)
    for code, info in sorted_cats:
        is_selected = code in current_list
        icon = "✅" if is_selected else "🔹"
        name = info['name']
        count = info['count']
        
        # Формуємо текст кнопки: Іконка + Назва + (Кількість)
        btn_text = f"{icon} {name} ({count})"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"cat_{code}")])
        
    # Кнопка Готово
    keyboard.append([InlineKeyboardButton(text="💾 Зберегти вибір", callback_data="cat_done")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)