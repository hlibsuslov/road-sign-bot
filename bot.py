import asyncio
import logging
import os
import re
import time
from datetime import date
from html import escape as escape_html, unescape as unescape_html

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
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
    get_details_keyboard,
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
HTML_TAG_RE = re.compile(r"</?(?:b|i|code)>")

BOT_COMMANDS = [
    BotCommand(command="start", description="Відкрити головне меню"),
    BotCommand(command="learn", description="Почати навчання"),
    BotCommand(command="stats", description="Переглянути статистику"),
    BotCommand(command="categories", description="Обрати категорії"),
    BotCommand(command="settings", description="Змінити налаштування"),
    BotCommand(command="reset", description="Скинути прогрес"),
]


# FSM States (тільки онбординг — навчання stateless, переживає рестарти)
class OnboardingStates(StatesGroup):
    choose_study_language = State()
    choose_translation_language = State()


# ==================== Допоміжні функції ====================

def h(value) -> str:
    """Екранує динамічний текст для Telegram HTML."""
    return escape_html(str(value or ""), quote=False)


def html_visible_length(text: str) -> int:
    """Довжина видимого тексту після розбору контрольованих HTML-тегів."""
    return len(unescape_html(HTML_TAG_RE.sub("", text)))


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
    text = f"<b>{h(sign['names'].get(study_lang, ''))}</b>\n"
    if trans_lang not in ("none", study_lang):
        name_trans = sign["names"].get(trans_lang, "")
        if name_trans:
            text += f"<i>{h(name_trans)}</i>\n"
    return text


def intro_card_text(sign_id: str, study_lang: str, trans_lang: str) -> str:
    sign = signs_main[sign_id]
    text = sign_name_block(sign_id, study_lang, trans_lang)
    text += f"\n{h(sign['descriptions'].get(study_lang, ''))}\n"
    if trans_lang not in ("none", study_lang):
        desc_trans = sign["descriptions"].get(trans_lang, "")
        if desc_trans:
            text += f"\n<i>{h(desc_trans)}</i>\n"
    category = sign["category"]["names"].get(study_lang, "")
    text += f"\n<b>Категорія:</b> {h(category)}"
    return text


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
            if html_visible_length(caption) <= CAPTION_LIMIT:
                await message.answer_photo(
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            else:
                logger.info("Підпис для знаку %s завеликий; надсилаємо окремим текстом", sign_id)
                await message.answer_photo(photo=photo)
                await message.answer(caption, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception as e:
            logger.error("Помилка відправки фото %s: %s", sign_id, e)
    await message.answer(caption, parse_mode=ParseMode.HTML, reply_markup=kb)


async def send_quiz(message: Message, user, sign_id: str):
    """Квіз: зображення знаку без назви + 4 варіанти відповіді."""
    study_lang = user["study_language"]
    options = learning.build_quiz_options(sign_id, signs_main, VALID_SIGNS, study_lang)
    progress = db.get_progress(user["user_id"], sign_id)
    box = progress["box"] if progress else 0

    caption = "❓ <b>Що означає цей знак?</b>"
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
        await message.answer("Спочатку відкрийте /start і налаштуйте бота.")
        return

    pool = get_study_pool(user)
    if not pool:
        await message.answer(
            "<b>Немає знаків для навчання</b>\n\n"
            "Оберіть інші категорії в головному меню.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
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
            "✅ <b>На зараз усе</b>\n\n"
            f"У черзі: {in_queue} знаків.\n"
        )
        kb = get_main_menu_keyboard()
        if nearest:
            wait = max(0, nearest["next_review_at"] - int(time.time()))
            text += f"Найближче повторення — через {h(learning.humanize_seconds(wait))}."
            kb = get_early_review_keyboard()
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


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
        "⚙️ <b>Налаштування</b>\n\n"
        f"<b>Мова знаків:</b> {h(study_lang_names.get(user['study_language'], user['study_language']))}\n"
        f"<b>Переклад:</b> {h(trans_lang_names.get(user['translation_language'], user['translation_language']))}\n"
        f"<b>Тема карток:</b> {h(theme_text)}\n"
        f"<b>Вивчено:</b> {mastered}/{len(VALID_SIGNS)}"
    )


def reset_prompt_text() -> str:
    return (
        "<b>Скинути весь прогрес?</b>\n\n"
        "Буде видалено рівні всіх знаків, історію відповідей і серію днів. "
        "Скасувати цю дію неможливо."
    )


# ==================== Старт та онбординг ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)

    if user is None:
        await state.set_data({"source": "onboarding"})
        await message.answer(
            "👋 <b>Вивчайте норвезькі дорожні знаки</b>\n\n"
            "Бот показує картки, перевіряє знання та повторює знаки через зростаючі інтервали.\n\n"
            "<b>Оберіть мову назв і квізів:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_language_keyboard()
        )
        await state.set_state(OnboardingStates.choose_study_language)
    else:
        await state.clear()
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
            f"👋 З поверненням, {message.from_user.first_name or 'друже'}!\n\n"
            f"Вивчено: {mastered}/{len(VALID_SIGNS)}\n"
            f"До повторення: {due}"
        )
        await message.answer(text, reply_markup=get_main_menu_keyboard())


@dp.callback_query(F.data.in_(["lang_no", "lang_en"]), StateFilter(OnboardingStates.choose_study_language))
async def choose_study_language(callback: CallbackQuery, state: FSMContext):
    study_lang = callback.data.split("_")[1]
    await callback.answer()
    await state.update_data(study_language=study_lang)

    await callback.message.edit_text(
        "<b>Оберіть мову перекладу:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_translation_keyboard()
    )
    await state.set_state(OnboardingStates.choose_translation_language)


@dp.callback_query(F.data == "lang_back", StateFilter(OnboardingStates.choose_translation_language))
async def language_back_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await callback.message.edit_text(
        "<b>Оберіть мову назв і квізів:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_keyboard(include_back=data.get("source") == "settings"),
    )
    await state.set_state(OnboardingStates.choose_study_language)


@dp.callback_query(F.data.startswith("trans_"), StateFilter(OnboardingStates.choose_translation_language))
async def choose_translation_language(callback: CallbackQuery, state: FSMContext):
    trans_lang = callback.data.split("_")[1]
    data = await state.get_data()
    study_lang = data.get("study_language")
    source = data.get("source", "onboarding")

    if study_lang not in {"no", "en"} or trans_lang not in {"none", "no", "en", "ru", "uk"}:
        await callback.answer("Не вдалося зберегти мови. Почніть з /start.", show_alert=True)
        await state.clear()
        return

    await callback.answer()

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

    await state.clear()

    if source == "settings":
        user = db.get_user(user_id)
        await callback.message.edit_text(
            build_settings_text(user),
            parse_mode=ParseMode.HTML,
            reply_markup=get_settings_keyboard(),
        )
        return

    await callback.message.edit_text(
        f"✅ <b>Налаштування збережено</b>\n\n"
        f"{h(summary)}\n"
        f"У базі: {len(VALID_SIGNS)} знаків.",
        parse_mode=ParseMode.HTML,
        reply_markup=None,
    )
    await callback.message.answer(
        f"Готові? Натисніть «{BTN_STUDY}».",
        reply_markup=get_main_menu_keyboard(),
    )


# ==================== Навчання ====================

@dp.message(Command("learn"))
@dp.message(F.text == BTN_STUDY)
async def cmd_learn(message: Message, state: FSMContext):
    await state.clear()
    await send_study_step(message, message.from_user.id)


@dp.callback_query(F.data == "study_next")
async def study_next_handler(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
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
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    if nearest:
        await send_quiz(callback.message, user, nearest["sign_id"])
    else:
        await callback.message.answer(
            "<b>Немає знаків для повторення</b>\n\n"
            "Оберіть «Вчитися», щоб відкрити наступний знак.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )


@dp.callback_query(F.data.startswith("q|"))
async def quiz_answer_handler(callback: CallbackQuery):
    parts = callback.data.split("|", 2)
    if len(parts) != 3:
        await callback.answer(
            "Ця кнопка вже не діє. Відкрийте новий квіз.",
            show_alert=True,
        )
        return
    _, sign_id, chosen_id = parts
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    if user is None or sign_id not in signs_main or chosen_id not in signs_main:
        await callback.answer(
            "Дані цього квізу вже недоступні. Відкрийте новий квіз.",
            show_alert=True,
        )
        return

    study_lang = user["study_language"]
    trans_lang = user["translation_language"]
    correct = (chosen_id == sign_id)
    now = int(time.time())
    await callback.answer("Правильно" if correct else "Неправильно")

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
        text = "✅ <b>Правильно</b>\n\n"
        text += sign_name_block(sign_id, study_lang, trans_lang)
        if new_box >= learning.MASTERED_BOX and progress["box"] < learning.MASTERED_BOX:
            text += "\n<b>Знак вивчено.</b> Він іноді повертатиметься для закріплення."
        else:
            wait = learning.humanize_seconds(next_review - now)
            text += f"\nРівень: {new_box}/{learning.MAX_BOX} · повторення через {h(wait)}"
    else:
        sign = signs_main[sign_id]
        text = "❌ <b>Неправильно</b>\n\nПравильна відповідь:\n"
        text += sign_name_block(sign_id, study_lang, trans_lang)
        text += f"\n{h(sign['descriptions'].get(study_lang, ''))}\n"
        text += "\nЦей знак повториться за кілька хвилин."

    kb = get_feedback_keyboard(sign_id)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode=ParseMode.HTML, reply_markup=kb
            )
        else:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramBadRequest as e:
        logger.warning("Не вдалось оновити повідомлення квізу: %s", e)


@dp.callback_query(F.data.startswith("know|"))
async def already_know_handler(callback: CallbackQuery):
    """«Вже знаю» на картці нового знаку — одразу позначаємо вивченим."""
    sign_id = callback.data.split("|", 1)[1]
    user_id = callback.from_user.id
    if db.get_user(user_id) is None or sign_id not in signs_main:
        await callback.answer(
            "Ця картка вже недоступна. Відкрийте новий знак.",
            show_alert=True,
        )
        return
    await callback.answer()
    now = int(time.time())
    box, next_review = learning.schedule_known(now)
    db.set_box(user_id, sign_id, box, next_review)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await send_study_step(callback.message, user_id)


@dp.callback_query(F.data.startswith("more|"))
async def more_info_handler(callback: CallbackQuery):
    sign_id = callback.data.split("|", 1)[1]
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Спочатку відкрийте /start.", show_alert=True)
        return

    study_lang = user["study_language"]
    trans_lang = user["translation_language"]
    sign_data = signs_main.get(sign_id)
    extra_data = signs_extra.get(sign_id)

    if not sign_data:
        await callback.answer("Дані цього знака вже недоступні.", show_alert=True)
        return

    await callback.answer()
    name = sign_data["names"].get(study_lang, "")
    text = f"ℹ️ <b>{h(name)}</b>\n\n"
    if extra_data and "extra" in extra_data:
        extra_text = extra_data["extra"].get(study_lang, "Додаткова інформація недоступна.")
        text += f"{h(extra_text)}\n"
        if trans_lang not in ("none", study_lang):
            extra_text_trans = extra_data["extra"].get(trans_lang, "")
            if extra_text_trans:
                text += f"\n<i>{h(extra_text_trans)}</i>"
    else:
        text += "Додаткова інформація для цього знаку недоступна."

    await callback.message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_details_keyboard(),
    )


# ==================== Статистика ====================

@dp.message(Command("stats"))
@dp.message(F.text == BTN_STATS)
async def cmd_stats(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)
    if not user:
        await message.answer("Спочатку відкрийте /start.")
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
        "📊 <b>Ваш прогрес</b>\n\n"
        f"<code>{bar}</code> {pct:.0f}%\n"
        f"Вивчено: {mastered}/{total}\n"
        f"На вивченні: {in_learning}\n"
        f"Нові: {new}\n"
        f"До повторення: {due_now}\n\n"
        "<b>Результати</b>\n"
    )
    if answered:
        text += (
            f"Точність: {accuracy} ({correct_total}/{answered})\n"
            f"Серія: {streak} дн.\n"
            f"Сьогодні: {today_answered} відповідей · {today_correct} правильних\n"
        )
    else:
        text += "Ще немає відповідей. Почніть навчання, щоб побачити точність і серію.\n"

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

    text += "\n<b>За категоріями</b>\n"
    for code, name in sorted(cat_names.items(), key=lambda x: x[1]):
        done = cat_mastered.get(code, 0)
        marker = "✓" if done == cat_totals[code] else "•"
        text += f"{marker} {h(name)} — {done}/{cat_totals[code]}\n"

    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


# ==================== Категорії ====================

@dp.message(Command("categories"))
@dp.message(F.text == BTN_CATEGORIES)
async def choose_category_handler(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Спочатку відкрийте /start.")
        return

    await message.answer(
        "📂 <b>Категорії для навчання</b>\n\n"
        "Торкніться категорії, щоб увімкнути або вимкнути її.\n"
        "✓ — обрано · ○ — не обрано\n\n"
        "Зміни зберігаються одразу.",
        parse_mode=ParseMode.HTML,
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

    valid_codes = {
        signs_main[s_id].get("category_code")
        for s_id in VALID_SIGNS
        if s_id in signs_main
    }
    if cat_code not in {"all", "done"} and cat_code not in valid_codes:
        await callback.answer("Ця категорія вже недоступна. Відкрийте список заново.", show_alert=True)
        return

    await callback.answer()
    study_lang = user["study_language"]
    current_cats_str = user["selected_category"] or 'all'

    if cat_code == 'all':
        new_cats_str = 'all'
    elif cat_code == 'done':
        selected_cats = current_cats_str.split(',') if current_cats_str != 'all' else ['all']
        if 'all' in selected_cats:
            count = len(VALID_SIGNS)
            cat_summary = "Обрано всі категорії"
        else:
            cat_summary = f"Обрано категорій: {len(selected_cats)}"
            count = sum(
                1 for s_id in VALID_SIGNS
                if signs_main.get(s_id, {}).get("category_code") in selected_cats
            )
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"✅ <b>Категорії оновлено</b>\n\n"
            f"{h(cat_summary)}\n"
            f"Знаків у добірці: {count}\n\n"
            f"Оберіть «{BTN_STUDY}», щоб продовжити.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard()
        )
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


# ==================== Налаштування ====================

@dp.message(Command("settings"))
@dp.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Спочатку відкрийте /start.")
        return
    await message.answer(
        build_settings_text(user),
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard(),
    )


@dp.callback_query(F.data == "settings_back")
async def settings_back_callback(callback: CallbackQuery, state: FSMContext):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        build_settings_text(user),
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard(),
    )


@dp.callback_query(F.data == "change_theme")
async def change_theme_menu(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "<b>Оберіть тему карток</b>\n\n"
        "Тема змінює фон зображень дорожніх знаків.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_theme_keyboard(user["theme"] or "light"),
    )


@dp.callback_query(F.data.startswith("theme_"))
async def set_theme_callback(callback: CallbackQuery):
    theme = callback.data.split("_")[1]
    user = db.get_user(callback.from_user.id)
    if not user or theme not in {"light", "dark"}:
        await callback.answer("Не вдалося змінити тему. Відкрийте налаштування заново.", show_alert=True)
        return
    await callback.answer()
    db.update_user_theme(callback.from_user.id, theme)
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        build_settings_text(user),
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard(),
    )


@dp.callback_query(F.data == "change_language")
async def change_language_handler(callback: CallbackQuery, state: FSMContext):
    if db.get_user(callback.from_user.id) is None:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    await callback.answer()
    await state.set_data({"source": "settings"})
    await state.set_state(OnboardingStates.choose_study_language)
    await callback.message.edit_text(
        "<b>Оберіть мову назв і квізів:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_keyboard(include_back=True),
    )


@dp.callback_query(F.data == "reset_progress")
async def reset_progress_handler(callback: CallbackQuery):
    if db.get_user(callback.from_user.id) is None:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        reset_prompt_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_reset_confirm_keyboard()
    )


@dp.callback_query(F.data == "reset_confirm")
async def reset_confirm_handler(callback: CallbackQuery, state: FSMContext):
    if db.get_user(callback.from_user.id) is None:
        await callback.answer("Спочатку /start", show_alert=True)
        return
    await callback.answer()
    db.reset_progress(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Прогрес скинуто</b>\n\nУсі знаки знову доступні для навчання.",
        parse_mode=ParseMode.HTML,
    )
    await callback.message.answer(
        f"Натисніть «{BTN_STUDY}», щоб почати спочатку.",
        reply_markup=get_main_menu_keyboard()
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    await state.clear()
    if db.get_user(message.from_user.id) is None:
        await message.answer("Спочатку відкрийте /start.")
        return
    await message.answer(
        reset_prompt_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_reset_confirm_keyboard()
    )


# ==================== Відхилення від сценарію ====================

@dp.callback_query()
async def unknown_callback_handler(callback: CallbackQuery):
    """Завершує спіннер для застарілих кнопок зі старих повідомлень."""
    await callback.answer(
        "Ця кнопка вже не діє. Відкрийте потрібний розділ заново.",
        show_alert=True,
    )


@dp.message(StateFilter(OnboardingStates.choose_study_language))
async def study_language_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        "Оберіть мову кнопкою нижче.",
        reply_markup=get_language_keyboard(include_back=data.get("source") == "settings"),
    )


@dp.message(StateFilter(OnboardingStates.choose_translation_language))
async def translation_language_prompt(message: Message):
    await message.answer(
        "Оберіть мову перекладу кнопкою нижче.",
        reply_markup=get_translation_keyboard(),
    )


@dp.message(StateFilter(None))
async def unknown_message_handler(message: Message):
    if db.get_user(message.from_user.id) is None:
        await message.answer("Відкрийте /start, щоб налаштувати бота.")
        return
    await message.answer(
        "Оберіть дію з меню нижче.",
        reply_markup=get_main_menu_keyboard(),
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
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer(
                "Не вдалося виконати дію. Спробуйте ще раз.",
                show_alert=True,
            )
        elif event.update.message:
            await event.update.message.answer(
                "Не вдалося обробити запит. Спробуйте ще раз або відкрийте /start."
            )
    except Exception:
        logger.warning("Не вдалося показати користувачу повідомлення про помилку")
    return True


# ==================== Запуск бота ====================

async def main():
    global VALID_SIGNS
    logger.info("Бот запускається...")
    db.init_db()

    # Перевірка картинок при старті
    VALID_SIGNS = validate_signs_integrity(signs_list)

    await bot.set_my_commands(BOT_COMMANDS)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
