import asyncio
import logging
import os
import time
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, BufferedInputFile, ErrorEvent, BotCommand
)
from aiogram.exceptions import TelegramBadRequest

import learning
from database import Database
from keyboards import (
    BTN_STUDY, BTN_STATS, BTN_CATEGORIES, BTN_SETTINGS,
    get_language_keyboard,
    get_translation_keyboard,
    get_main_menu_keyboard,
    get_settings_keyboard,
    get_theme_keyboard,
    get_categories_keyboard,
    get_intro_keyboard,
    get_quiz_keyboard,
    get_feedback_keyboard,
    get_early_review_keyboard,
    get_reset_confirm_keyboard,
)
from utils import (
    load_signs_main,
    load_signs_extra,
    load_signs_list,
    find_sign_image,
    process_sign_image,
    validate_signs_integrity,
)

# Налаштування логування (deployment probe 2026-07-16)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database(db_path=os.getenv("DB_PATH", "road_signs_bot.db"))

# Завантаження даних
signs_main = load_signs_main()
signs_extra = load_signs_extra()
signs_list = load_signs_list()

# Внутрішній список перевірених, валідних знаків
VALID_SIGNS = []

CAPTION_LIMIT = 1024


# FSM States (тільки онбординг — навчання stateless, переживає рестарти)
class OnboardingStates(StatesGroup):
    choose_study_language = State()
    choose_translation_language = State()


# ==================== Допоміжні функції ====================

def clamp_caption(text: str) -> str:
    if len(text) <= CAPTION_LIMIT:
        return text
    return text[:CAPTION_LIMIT - 1] + "…"


def get_study_pool(user) -> list:
    """Валідні знаки з урахуванням обраних користувачем категорій."""
    cats_str = user["selected_category"] or 'all'
    if cats_str == 'all':
        return list(VALID_SIGNS)
    selected = set(cats_str.split(','))
    return [
        s for s in VALID_SIGNS
        if signs_main.get(s, {}).get("category_code") in selected
    ]


def sign_name_block(sign_id: str, study_lang: str, trans_lang: str) -> str:
    """Назва знаку + переклад (якщо налаштований)."""
    sign = signs_main[sign_id]
    text = f"📍 *{sign['names'].get(study_lang, '')}*\n"
    if trans_lang not in ("none", study_lang):
        name_trans = sign["names"].get(trans_lang, "")
        if name_trans:
            text += f"_{name_trans}_\n"
    return text


def intro_card_text(sign_id: str, study_lang: str, trans_lang: str) -> str:
    sign = signs_main[sign_id]
    text = "🆕 *Новий знак*\n\n"
    text += sign_name_block(sign_id, study_lang, trans_lang)
    text += f"\n{sign['descriptions'].get(study_lang, '')}\n"
    if trans_lang not in ("none", study_lang):
        desc_trans = sign["descriptions"].get(trans_lang, "")
        if desc_trans:
            text += f"_{desc_trans}_\n"
    category = sign["category"]["names"].get(study_lang, "")
    text += f"\n*Категорія:* {category}"
    return clamp_caption(text)


async def send_sign_photo(message: Message, sign_id: str, theme: str, caption: str, kb):
    """Надсилає знак з обробленим зображенням; за збою — текстом."""
    image_path = find_sign_image(sign_id)
    if image_path:
        try:
            processed = process_sign_image(image_path, theme=theme)
            if processed:
                photo = BufferedInputFile(processed.read(), filename=f"{sign_id}.jpg")
            else:
                photo = FSInputFile(image_path)
            await message.answer_photo(
                photo=photo, caption=caption, parse_mode="Markdown", reply_markup=kb
            )
            return
        except Exception as e:
            logger.error("Помилка відправки фото %s: %s", sign_id, e)
    await message.answer(caption, parse_mode="Markdown", reply_markup=kb)


async def send_quiz(message: Message, user, sign_id: str):
    """Квіз: зображення знаку без назви + 4 варіанти відповіді."""
    study_lang = user["study_language"]
    options = learning.build_quiz_options(sign_id, signs_main, VALID_SIGNS, study_lang)
    progress = db.get_progress(user["user_id"], sign_id)
    box = progress["box"] if progress else 0

    caption = "❓ *Що означає цей знак?*"
    if box > 0:
        caption += f"\n\n🔁 Повторення • рівень {box}/{learning.MAX_BOX}"
    kb = get_quiz_keyboard(sign_id, options, signs_main, study_lang)
    await send_sign_photo(message, sign_id, user["theme"] or 'light', caption, kb)


async def send_intro(message: Message, user, sign_id: str):
    """Знайомство з новим знаком + постановка в чергу повторень."""
    now = int(time.time())
    box, next_review = learning.schedule_after_intro(now)
    db.introduce_sign(user["user_id"], sign_id, box, next_review)

    caption = intro_card_text(sign_id, user["study_language"], user["translation_language"])
    await send_sign_photo(
        message, sign_id, user["theme"] or 'light', caption, get_intro_keyboard(sign_id)
    )


async def send_study_step(message: Message, user_id: int):
    """Головний цикл навчання: повторення -> нові знаки -> «все повторено»."""
    user = db.get_user(user_id)
    if user is None:
        await message.answer("Спочатку використайте /start для налаштування бота.")
        return

    pool = get_study_pool(user)
    if not pool:
        await message.answer(
            "У обраних категоріях немає знаків. Оберіть інші категорії в меню 📂."
        )
        return

    progress_map = db.get_progress_map(user_id)
    sign_id, mode = learning.pick_next(pool, progress_map)

    if mode == "review":
        await send_quiz(message, user, sign_id)
    elif mode == "new":
        await send_intro(message, user, sign_id)
    else:
        # Все повторено, нових знаків немає — кажемо, коли повертатись
        nearest = learning.earliest_due(pool, progress_map)
        in_queue = sum(1 for s in pool if s in progress_map)
        text = (
            "🎉 *На зараз усе!*\n\n"
            f"У черзі повторень: {in_queue} знаків.\n"
        )
        kb = None
        if nearest:
            wait = max(0, nearest["next_review_at"] - int(time.time()))
            text += f"Найближче повторення: через {learning.humanize_seconds(wait)}."
            kb = get_early_review_keyboard()
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


def build_settings_text(user) -> str:
    study_lang_names = {"no": "Норвезька", "en": "Англійська"}
    trans_lang_names = {"no": "Норвезька", "en": "Англійська", "ru": "Російська",
                        "uk": "Українська", "none": "Без перекладу"}
    theme_text = "Світла ☀️" if (user["theme"] or 'light') == 'light' else "Темна 🌑"
    progress_map = db.get_progress_map(user["user_id"])
    mastered = sum(
        1 for s, p in progress_map.items()
        if s in set(VALID_SIGNS) and p["box"] >= learning.MASTERED_BOX
    )
    return (
        f"⚙️ *Налаштування*\n\n"
        f"Мова вивчення: {study_lang_names.get(user['study_language'], user['study_language'])}\n"
        f"Мова перекладу: {trans_lang_names.get(user['translation_language'], user['translation_language'])}\n"
        f"Тема: {theme_text}\n"
        f"Вивчено знаків: {mastered}/{len(VALID_SIGNS)}"
    )


# ==================== Старт та онбординг ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)

    if user is None:
        await message.answer(
            "Вітаю! 👋\n\n"
            "Цей бот допоможе вам вивчити дорожні знаки за методикою "
            "інтервальних повторень: знайомство зі знаком, перевірки у форматі "
            "квізу та повторення через зростаючі проміжки часу.\n\n"
            "Якою мовою ви плануєте вивчати дорожні знаки?",
            reply_markup=get_language_keyboard()
        )
        await state.set_state(OnboardingStates.choose_study_language)
    else:
        db.touch_user(user_id)
        progress_map = db.get_progress_map(user_id)
        valid_set = set(VALID_SIGNS)
        mastered = sum(
            1 for s, p in progress_map.items()
            if s in valid_set and p["box"] >= learning.MASTERED_BOX
        )
        now = int(time.time())
        due = sum(
            1 for s, p in progress_map.items()
            if s in valid_set and p["next_review_at"] <= now
        )
        text = (
            f"З поверненням, {message.from_user.first_name}! 👋\n\n"
            f"✅ Вивчено: {mastered}/{len(VALID_SIGNS)}\n"
            f"⏰ Готові до повторення: {due}"
        )
        await message.answer(text, reply_markup=get_main_menu_keyboard())


@dp.callback_query(F.data.in_(["lang_no", "lang_en"]), StateFilter(OnboardingStates.choose_study_language))
async def choose_study_language(callback: CallbackQuery, state: FSMContext):
    study_lang = callback.data.split("_")[1]
    await state.update_data(study_language=study_lang)

    await callback.message.edit_text(
        "Якою мовою ви хочете бачити переклад назви дорожнього знаку?",
        reply_markup=get_translation_keyboard()
    )
    await state.set_state(OnboardingStates.choose_translation_language)
    await callback.answer()


@dp.callback_query(F.data.startswith("trans_"), StateFilter(OnboardingStates.choose_translation_language))
async def choose_translation_language(callback: CallbackQuery, state: FSMContext):
    trans_lang = callback.data.split("_")[1]
    data = await state.get_data()
    study_lang = data.get("study_language")

    user_id = callback.from_user.id
    db.upsert_user(user_id, study_lang, trans_lang)

    study_lang_names = {"no": "норвезькою", "en": "англійською"}
    trans_lang_names = {"no": "норвезьку", "en": "англійську", "ru": "російську",
                        "uk": "українську", "none": "жодну"}
    study_lang_text = study_lang_names.get(study_lang, study_lang)
    trans_lang_text = trans_lang_names.get(trans_lang, trans_lang)

    if trans_lang == "none":
        summary = f"Ви плануєте вивчати дорожні знаки {study_lang_text} мовою без перекладу."
    else:
        summary = f"Ви плануєте вивчати дорожні знаки {study_lang_text} мовою з перекладом на {trans_lang_text}."

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"{summary}\n\n"
        f"Налаштування збережено ✅\n\n"
        f"Всього знаків для вивчення: {len(VALID_SIGNS)}\n\n"
        f"*Як це працює:*\n"
        f"1️⃣ Бот показує новий знак з описом.\n"
        f"2️⃣ Через деякий час перевіряє вас квізом.\n"
        f"3️⃣ Правильні відповіді збільшують інтервал повторення, "
        f"помилки повертають знак на початок.\n"
        f"4️⃣ Знак вважається вивченим після {learning.MASTERED_BOX} рівнів перевірок.\n\n"
        f"Натисніть «{BTN_STUDY}», щоб почати!",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
    await state.clear()
    await callback.answer()


# ==================== Навчання ====================

@dp.message(Command("learn"))
@dp.message(F.text == BTN_STUDY)
async def cmd_learn(message: Message):
    await send_study_step(message, message.from_user.id)


@dp.callback_query(F.data == "study_next")
async def study_next_handler(callback: CallbackQuery):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer()
    await send_study_step(callback.message, callback.from_user.id)


@dp.callback_query(F.data == "study_early")
async def study_early_handler(callback: CallbackQuery):
    """Дострокове повторення: квіз на найближчий за розкладом знак."""
    user = db.get_user(callback.from_user.id)
    if user is None:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    pool = get_study_pool(user)
    progress_map = db.get_progress_map(user["user_id"])
    nearest = learning.earliest_due(pool, progress_map)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer()
    if nearest:
        await send_quiz(callback.message, user, nearest["sign_id"])
    else:
        await callback.message.answer("Немає знаків для повторення.")


@dp.callback_query(F.data.startswith("q|"))
async def quiz_answer_handler(callback: CallbackQuery):
    _, sign_id, chosen_id = callback.data.split("|", 2)
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    if user is None or sign_id not in signs_main:
        await callback.answer("Помилка: дані не знайдено", show_alert=True)
        return

    study_lang = user["study_language"]
    trans_lang = user["translation_language"]
    correct = (chosen_id == sign_id)
    now = int(time.time())

    progress = db.get_progress(user_id, sign_id)
    if progress is None:
        # Прогрес міг бути скинутий між показом квізу та відповіддю
        box, next_review = learning.schedule_after_intro(now)
        db.introduce_sign(user_id, sign_id, box, next_review)
        progress = db.get_progress(user_id, sign_id)

    new_box, next_review = learning.schedule_after_answer(progress["box"], correct, now)
    db.record_answer(user_id, sign_id, correct, new_box, next_review)

    # Формуємо фідбек
    if correct:
        text = "✅ *Правильно!*\n\n"
        text += sign_name_block(sign_id, study_lang, trans_lang)
        if new_box >= learning.MASTERED_BOX and progress["box"] < learning.MASTERED_BOX:
            text += "\n🎉 *Знак вивчено!* Він зрідка повертатиметься для закріплення."
        else:
            wait = learning.humanize_seconds(next_review - now)
            text += f"\n📈 Рівень: {new_box}/{learning.MAX_BOX} • повторення через {wait}"
    else:
        sign = signs_main[sign_id]
        text = "❌ *Неправильно.* Правильна відповідь:\n\n"
        text += sign_name_block(sign_id, study_lang, trans_lang)
        text += f"\n{sign['descriptions'].get(study_lang, '')}\n"
        text += "\n🔁 Цей знак повториться за кілька хвилин."

    text = clamp_caption(text)
    kb = get_feedback_keyboard(sign_id)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="Markdown", reply_markup=kb
            )
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest as e:
        logger.warning("Не вдалось оновити повідомлення квізу: %s", e)
    await callback.answer("✅ Правильно!" if correct else "❌ Неправильно")


@dp.callback_query(F.data.startswith("know|"))
async def already_know_handler(callback: CallbackQuery):
    """«Вже знаю» на картці нового знаку — одразу позначаємо вивченим."""
    sign_id = callback.data.split("|", 1)[1]
    user_id = callback.from_user.id
    now = int(time.time())
    box, next_review = learning.schedule_known(now)
    db.set_box(user_id, sign_id, box, next_review)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("Знак позначено як вивчений ✅")
    await send_study_step(callback.message, user_id)


@dp.callback_query(F.data.startswith("more|"))
async def more_info_handler(callback: CallbackQuery):
    sign_id = callback.data.split("|", 1)[1]
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Помилка: користувач не знайдений")
        return

    study_lang = user["study_language"]
    trans_lang = user["translation_language"]
    sign_data = signs_main.get(sign_id)
    extra_data = signs_extra.get(sign_id)

    if not sign_data:
        await callback.answer("Знак не знайдено")
        return

    name = sign_data["names"].get(study_lang, "")
    text = f"📍 *{name}*\n\n"
    if extra_data and "extra" in extra_data:
        extra_text = extra_data["extra"].get(study_lang, "Додаткова інформація недоступна.")
        text += f"{extra_text}\n"
        if trans_lang not in ("none", study_lang):
            extra_text_trans = extra_data["extra"].get(trans_lang, "")
            if extra_text_trans:
                text += f"\n_{extra_text_trans}_"
    else:
        text += "Додаткова інформація для цього знаку недоступна."

    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


# ==================== Статистика ====================

@dp.message(Command("stats"))
@dp.message(F.text == BTN_STATS)
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    if not user:
        await message.answer("Спочатку використайте /start")
        return

    valid_set = set(VALID_SIGNS)
    total = len(VALID_SIGNS)
    progress_map = {s: p for s, p in db.get_progress_map(user_id).items() if s in valid_set}
    now = int(time.time())

    mastered = sum(1 for p in progress_map.values() if p["box"] >= learning.MASTERED_BOX)
    in_learning = len(progress_map) - mastered
    new = total - len(progress_map)
    due_now = sum(1 for p in progress_map.values() if p["next_review_at"] <= now)

    answered, correct_total = db.get_answer_totals(user_id)
    accuracy = f"{correct_total / answered * 100:.0f}%" if answered else "—"
    today_answered, today_correct = db.get_day_stats(user_id, date.today().isoformat())
    streak = learning.count_streak(db.get_active_days(user_id))

    pct = mastered / total * 100 if total else 0
    bar = learning.progress_bar(mastered, total)

    text = (
        f"📊 *Статистика*\n\n"
        f"{bar} {pct:.0f}%\n"
        f"✅ Вивчено: {mastered}/{total}\n"
        f"📚 На вивченні: {in_learning}\n"
        f"🆕 Нових: {new}\n\n"
        f"🎯 Точність: {accuracy} ({correct_total}/{answered})\n"
        f"🔥 Серія: {streak} дн поспіль\n"
        f"📅 Сьогодні: {today_answered} відповідей, {today_correct} правильних\n"
        f"⏰ Готові до повторення: {due_now}\n"
    )

    # Розбивка вивченого по категоріях
    cat_totals, cat_mastered, cat_names = {}, {}, {}
    for s_id in VALID_SIGNS:
        data = signs_main.get(s_id)
        if not data:
            continue
        code = data.get("category_code")
        cat_totals[code] = cat_totals.get(code, 0) + 1
        if code not in cat_names:
            cat_names[code] = data["category"]["names"].get("uk") or \
                data["category"]["names"].get(user["study_language"], code)
        p = progress_map.get(s_id)
        if p and p["box"] >= learning.MASTERED_BOX:
            cat_mastered[code] = cat_mastered.get(code, 0) + 1

    text += "\n*По категоріях:*\n"
    for code, name in sorted(cat_names.items(), key=lambda x: x[1]):
        done = cat_mastered.get(code, 0)
        icon = "✅" if done == cat_totals[code] else "▪️"
        text += f"{icon} {name}: {done}/{cat_totals[code]}\n"

    await message.answer(text, parse_mode="Markdown")


# ==================== Категорії ====================

@dp.message(F.text == BTN_CATEGORIES)
async def choose_category_handler(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Спочатку /start")
        return

    await message.answer(
        "📂 *Вибір категорій*\n\n"
        "Оберіть категорії для вивчення.\n\n"
        "✅ — категорія обрана\n"
        "🔹 — категорія пропущена\n\n"
        "Натисніть «Зберегти вибір», коли закінчите.",
        parse_mode="Markdown",
        reply_markup=get_categories_keyboard(
            signs_main, user["study_language"], user["selected_category"] or 'all', VALID_SIGNS
        )
    )


@dp.callback_query(F.data.startswith("cat_"))
async def set_category_callback(callback: CallbackQuery):
    cat_code = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    if not user:
        await callback.answer("Спочатку /start", show_alert=True)
        return

    study_lang = user["study_language"]
    current_cats_str = user["selected_category"] or 'all'

    if cat_code == 'all':
        new_cats_str = 'all'
    elif cat_code == 'done':
        selected_cats = current_cats_str.split(',') if current_cats_str != 'all' else ['all']
        if 'all' in selected_cats:
            count = len(VALID_SIGNS)
            cat_summary = "Всі категорії"
        else:
            cat_summary = f"{len(selected_cats)} категорій"
            count = sum(
                1 for s_id in VALID_SIGNS
                if signs_main.get(s_id, {}).get("category_code") in selected_cats
            )
        await callback.message.delete()
        await callback.message.answer(
            f"💾 *Налаштування збережено!*\n\n"
            f"📂 Обрано: {cat_summary}\n"
            f"🔢 Всього знаків: {count}\n\n"
            f"Натисніть «{BTN_STUDY}», щоб продовжити.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()
        return
    else:
        current_list = current_cats_str.split(',') if current_cats_str != 'all' else []
        if cat_code in current_list:
            current_list.remove(cat_code)
        else:
            current_list.append(cat_code)
        new_cats_str = ",".join(current_list) if current_list else 'all'

    db.update_user_categories(user_id, new_cats_str)
    await callback.message.edit_reply_markup(
        reply_markup=get_categories_keyboard(signs_main, study_lang, new_cats_str, VALID_SIGNS)
    )
    await callback.answer()


# ==================== Налаштування ====================

@dp.message(Command("settings"))
@dp.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Спочатку використайте /start")
        return
    await message.answer(
        build_settings_text(user), parse_mode="Markdown", reply_markup=get_settings_keyboard()
    )


@dp.callback_query(F.data == "settings_back")
async def settings_back_callback(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    await callback.message.edit_text(
        build_settings_text(user), parse_mode="Markdown", reply_markup=get_settings_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "change_theme")
async def change_theme_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Оберіть тему оформлення карток:",
        reply_markup=get_theme_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("theme_"))
async def set_theme_callback(callback: CallbackQuery):
    theme = callback.data.split("_")[1]
    db.update_user_theme(callback.from_user.id, theme)
    theme_name = "Світла ☀️" if theme == "light" else "Темна 🌑"
    await callback.message.edit_text(
        f"Тему змінено на: {theme_name}",
        reply_markup=get_theme_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "change_language")
async def change_language_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Якою мовою ви плануєте вивчати дорожні знаки?",
        reply_markup=get_language_keyboard()
    )
    await state.set_state(OnboardingStates.choose_study_language)
    await callback.answer()


@dp.callback_query(F.data == "reset_progress")
async def reset_progress_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚠️ *Скинути весь прогрес?*\n\n"
        "Будуть видалені рівні всіх знаків та вся статистика. Це незворотньо.",
        parse_mode="Markdown",
        reply_markup=get_reset_confirm_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "reset_confirm")
async def reset_confirm_handler(callback: CallbackQuery, state: FSMContext):
    db.reset_progress(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "✅ Прогрес скинуто! Всі знаки знову доступні для вивчення."
    )
    await callback.message.answer(
        f"Натисніть «{BTN_STUDY}», щоб почати спочатку.",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    await message.answer(
        "⚠️ *Скинути весь прогрес?*\n\n"
        "Будуть видалені рівні всіх знаків та вся статистика. Це незворотньо.",
        parse_mode="Markdown",
        reply_markup=get_reset_confirm_keyboard()
    )


# ==================== Обробка помилок ====================

@dp.errors()
async def on_error(event: ErrorEvent):
    """Глобальний обробник помилок aiogram.

    Найчастіший кейс — користувач тапає кнопку, що перемальовує повідомлення
    з тим самим текстом/розміткою: Telegram відхиляє no-op редагування з
    `message is not modified`. Це безпечно — просто ігноруємо. Решту помилок
    логуємо з трейсбеком, але позначаємо обробленими, щоб polling не зупинявся.
    """
    exc = event.exception
    if isinstance(exc, TelegramBadRequest) and "message is not modified" in str(exc).lower():
        return True
    logger.exception("Необроблена помилка при обробці апдейту: %r", exc)
    return True


# ==================== Запуск бота ====================

async def main():
    global VALID_SIGNS
    logger.info("Бот запускається...")
    db.init_db()

    # Перевірка картинок при старті
    VALID_SIGNS = validate_signs_integrity(signs_list)

    await bot.set_my_commands([
        BotCommand(command="learn", description="🎓 Вчитися"),
        BotCommand(command="stats", description="📊 Статистика"),
        BotCommand(command="settings", description="⚙️ Налаштування"),
        BotCommand(command="reset", description="🔄 Скинути прогрес"),
    ])

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
