import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, ErrorEvent
from aiogram.exceptions import TelegramBadRequest
from database import Database
from keyboards import (
    get_language_keyboard, 
    get_translation_keyboard, 
    get_card_keyboard, 
    get_main_menu_keyboard, 
    get_settings_keyboard,
    get_theme_keyboard,
    get_categories_keyboard
)
from utils import (
    load_signs_main, 
    load_signs_extra, 
    load_signs_list, 
    find_sign_image, 
    process_sign_image,
    validate_signs_integrity
)
import random

# Налаштування логування
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

# FSM States
class OnboardingStates(StatesGroup):
    choose_study_language = State()
    choose_translation_language = State()

class LearningStates(StatesGroup):
    viewing_card = State()

# ==================== Обробники команд ====================

# Внутрішній список перевірених, валідних знаків
VALID_SIGNS = []

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if user is None:
        # Новий користувач - починаємо анкетування
        # Дефолтні значення для нових колонок, якщо раптом вони не записались
        # Але краще це робити після вибору мов.
        
        await message.answer(
            "Вітаю! 👋\n\n"
            "Цей бот допоможе вам вивчити дорожні знаки.\n\n"
            "Якою мовою ви плануєте вивчати дорожні знаки?",
            reply_markup=get_language_keyboard()
        )
        await state.set_state(OnboardingStates.choose_study_language)
    else:
        # Користувач вже зареєстрований
        # Перевіряємо наявність нових колонок, хоча б читанням (database міграція вже мала б спрацювати)
        
        await message.answer(
            f"З поверненням, {message.from_user.first_name}! 👋\n\n"
            f"Вивчено знаків: {len(db.get_learned_signs(user_id))}/{len(VALID_SIGNS)}",
            reply_markup=get_main_menu_keyboard()
        )

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
    
    # Зберігаємо користувача в БД
    user_id = callback.from_user.id
    db.add_user(user_id, study_lang, trans_lang)
    
    # Формуємо підсумкове повідомлення
    study_lang_names = {"no": "норвезькою", "en": "англійською"}
    trans_lang_names = {"no": "норвезьку", "en": "англійську", "ru": "російську", "uk": "українську", "none": "жодну"}
    
    study_lang_text = study_lang_names.get(study_lang, study_lang)
    trans_lang_text = trans_lang_names.get(trans_lang, trans_lang)
    
    if trans_lang == "none":
        summary = f"Ви плануєте вивчати дорожні знаки {study_lang_text} мовою без перекладу на жодну мову."
    else:
        summary = f"Ви плануєте вивчати дорожні знаки {study_lang_text} мовою з перекладом на {trans_lang_text} мову."
    
    # Видаляємо інлайн клавіатуру з попереднього повідомлення
    await callback.message.edit_reply_markup(reply_markup=None)
    
    await callback.message.answer(
        f"{summary}\n\n"
        f"Налаштування збережено ✅\n\n"
        f"Всього знаків для вивчення: {len(VALID_SIGNS)}\n\n",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.clear()
    await callback.answer()

@dp.message(Command("learn"))
async def cmd_learn(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if user is None:
        await message.answer("Спочатку використайте /start для налаштування бота.")
        return
    
    # Отримуємо невивчені знаки
    learned_signs = set(db.get_learned_signs(user_id))
    unlearned_signs = [s for s in signs_list if s not in learned_signs]
    
    if not unlearned_signs:
        await message.answer(
            "🎉 Вітаю! Ви вивчили всі знаки!\n\n"
            "Використайте /reset щоб почати спочатку."
        )
        return
    
    # Вибираємо випадковий знак
    sign_id = random.choice(unlearned_signs)
    await show_sign_card(message, user_id, sign_id, state)

@dp.message(F.text == "Нова карточка")
async def start_learning_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if user is None:
        await message.answer("Спочатку використайте /start для налаштування бота.")
        return
    
    # Витягуємо налаштування користувача
    selected_cats_str = user[4] if len(user) > 4 else 'all'
    selected_cats = selected_cats_str.split(',') if selected_cats_str != 'all' else ['all']
    
    learned_signs = set(db.get_learned_signs(user_id))
    
    # Фільтруємо спочатку за валідністю (наявність фото)
    available_signs = [s for s in VALID_SIGNS if s not in learned_signs]
    
    # Тепер фільтруємо за категорією
    if 'all' not in selected_cats:
        filtered_signs = []
        for s_id in available_signs:
            sign_info = signs_main.get(s_id)
            if sign_info and sign_info.get("category_code") in selected_cats:
                filtered_signs.append(s_id)
        available_signs = filtered_signs
    
    if not available_signs:
        if 'all' in selected_cats:
            await message.answer(
                "🎉 *Вітаю! Ви вивчили всі знаки!*\n\n"
                "Використайте /reset щоб почати спочатку.",
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                f"🎉 *Ви вивчили всі знаки в обраних категоріях!*\n\n"
                "Оберіть інші категорії або скиньте прогрес.",
                parse_mode="Markdown"
            )
        return
    
    sign_id = random.choice(available_signs)
    await show_sign_card(message, user_id, sign_id, state)

@dp.message(F.text == "📂 Категорії")
async def choose_category_handler(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await message.answer("Спочатку /start")
        return
        
    study_lang = user[1]
    current_cats_str = user[4] if len(user) > 4 else 'all'
    
    await message.answer(
        "📂 *Вибір категорій*\n\n"
        "Оберіть категорії зі списку нижче. Натискайте на кнопки, щоб додати або прибрати категорію з вивчення.\n\n"
        "✅ — категорія обрана\n"
        "🔹 — категорія пропущена\n\n"
        "Натисніть 'Зберегти вибір', коли закінчите.",
        parse_mode="Markdown",
        reply_markup=get_categories_keyboard(signs_main, study_lang, current_cats_str, VALID_SIGNS)
    )

@dp.callback_query(F.data.startswith("cat_"))
async def set_category_callback(callback: CallbackQuery):
    cat_code = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    study_lang = user[1]
    
    current_cats_str = user[4] if len(user) > 4 else 'all'
    
    # Логіка оновлення списку категорій
    if cat_code == 'all':
        new_cats_str = 'all'
    elif cat_code == 'done':
        # Формуємо звіт про обрані категорії
        selected_cats = current_cats_str.split(',') if current_cats_str != 'all' else ['all']
        
        count = 0
        if 'all' in selected_cats:
            count = len(VALID_SIGNS)
            cat_summary = "Всі категорії"
        else:
            cat_summary = f"{len(selected_cats)} категорій"
            # Рахуємо точну кількість доступних валідних знаків у вибраних категоріях
            for s_id in VALID_SIGNS:
                s_info = signs_main.get(s_id)
                if s_info and s_info.get("category_code") in selected_cats:
                    count += 1
        
        await callback.message.delete()
        await callback.message.answer(
            f"💾 *Налаштування збережено!*\n\n"
            f"📂 **Обрано:** {cat_summary}\n"
            f"🔢 **Всього знаків:** {count}\n\n"
            f"Натисніть 'Нова карточка', щоб почати вивчення обраних знаків.",
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
            
        if not current_list:
            new_cats_str = 'all' # Якщо нічого не обрано, скидаємо на "Всі"
        else:
            new_cats_str = ",".join(current_list)
    
    db.update_user_categories(user_id, new_cats_str)
    
    # Оновлюємо клавіатуру, щоб показати зміни
    await callback.message.edit_reply_markup(
        reply_markup=get_categories_keyboard(signs_main, study_lang, new_cats_str, VALID_SIGNS)
    )
    await callback.answer()

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await message.answer("Спочатку використайте /start")
        return
    
    study_lang_names = {"no": "Норвезька", "en": "Англійська"}
    trans_lang_names = {"no": "Норвезька", "en": "Англійська", "ru": "Російська", "uk": "Українська", "none": "Без перекладу"}
    
    study_lang = study_lang_names.get(user[1], user[1])
    trans_lang = trans_lang_names.get(user[2], user[2])
    learned_count = len(db.get_learned_signs(user_id))
    
    text = (
        f"⚙️ *Налаштування*\n\n"
        f"**Мова вивчення:** {study_lang}\n"
        f"**Мова перекладу:** {trans_lang}\n"
        f"**Вивчено знаків:** {learned_count}/{len(signs_list)}"
    )
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_settings_keyboard())

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await message.answer("Спочатку використайте /start")
        return
    
    learned_count = len(db.get_learned_signs(user_id))
    total_count = len(signs_list)
    percentage = (learned_count / total_count * 100) if total_count > 0 else 0
    
    text = (
        f"📊 Статистика\n\n"
        f"Вивчено знаків: {learned_count} з {total_count}\n"
        f"Прогрес: {percentage:.1f}%\n"
        f"Залишилось: {total_count - learned_count}"
    )
    
    await message.answer(text, parse_mode="Markdown")

async def show_sign_card(message: Message, user_id: int, sign_id: str, state: FSMContext):
    user = db.get_user(user_id)
    study_lang = user[1]
    trans_lang = user[2]
    # Отримуємо тему користувача
    theme = user[3] if len(user) > 3 else 'light'
    if theme is None: theme = 'light'
    
    sign_data = signs_main.get(sign_id)
    if not sign_data:
        await message.answer("Помилка: знак не знайдено.")
        return
    
    # Формуємо текст картки
    name = sign_data["names"].get(study_lang, "")
    description = sign_data["descriptions"].get(study_lang, "")
    category = sign_data["category"]["names"].get(study_lang, "")
    
    text = f"📍 *{name}*\n"
    
    # Додаємо переклад, якщо мова перекладу відрізняється від мови вивчення
    if trans_lang != "none" and trans_lang != study_lang:
        name_trans = sign_data["names"].get(trans_lang, "")
        text += f"_{name_trans}_\n"
    
    text += f"\n{description}\n"
    
    if trans_lang != "none" and trans_lang != study_lang:
        description_trans = sign_data["descriptions"].get(trans_lang, "")
        text += f"_{description_trans}_\n"
    
    text += f"\n*Категорія:* {category}"
    
    # Знаходимо картинку
    image_path = find_sign_image(sign_id)
    
    # Зберігаємо ID поточного знаку
    await state.update_data(current_sign_id=sign_id)
    await state.set_state(LearningStates.viewing_card)
    
    # Відправляємо картку
    if image_path:
        try:
            # Обробляємо зображення (додаємо фон відповідно до теми)
            processed_image = process_sign_image(image_path, theme=theme)
            
            if processed_image:
                photo = BufferedInputFile(processed_image.read(), filename=f"{sign_id}.jpg")
            else:
                # Fallback якщо обробка не вдалась
                photo = FSInputFile(image_path)
            
            await message.answer_photo(
                photo=photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_card_keyboard(sign_id)
            )
        except Exception as e:
            logger.error(f"Помилка відправки фото: {e}")
            await message.answer(text, parse_mode="Markdown", reply_markup=get_card_keyboard(sign_id))
    else:
        # Цей кейс теоретично не має статися, якщо працює валідація при запуску
        await message.answer(text, parse_mode="Markdown", reply_markup=get_card_keyboard(sign_id))

@dp.callback_query(F.data == "already_know")
async def already_know_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    sign_id = data.get("current_sign_id")
    
    if sign_id:
        db.add_learned_sign(user_id, sign_id)
        await callback.answer("Знак додано до вивчених! ✅")
        
        # Логіка вибору наступного знаку (враховуючи категорію)
        user = db.get_user(user_id)
        selected_cats_str = user[4] if len(user) > 4 else 'all'
        
        # Парсимо обрані категорії
        selected_cats = selected_cats_str.split(',') if selected_cats_str != 'all' else ['all']

        learned_signs = set(db.get_learned_signs(user_id))
        available_signs = [s for s in VALID_SIGNS if s not in learned_signs] # Використовуємо VALID_SIGNS
        
        if 'all' not in selected_cats:
            filtered_signs = []
            for s_id in available_signs:
                sign_info = signs_main.get(s_id)
                if sign_info and sign_info.get("category_code") in selected_cats:
                    filtered_signs.append(s_id)
            available_signs = filtered_signs
        
        if available_signs:
            next_sign_id = random.choice(available_signs)
            await callback.message.delete()
            await show_sign_card(callback.message, user_id, next_sign_id, state)
        else:
            await callback.message.edit_caption(
                caption="🎉 *Вітаю! Ви вивчили всі знаки в обраних категоріях!*",
                parse_mode="Markdown",
                reply_markup=None
            )
            await state.clear()

@dp.callback_query(F.data.startswith("more_"))
async def more_info_handler(callback: CallbackQuery):
    sign_id = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await callback.answer("Помилка: користувач не знайдений")
        return
    
    study_lang = user[1]
    trans_lang = user[2]
    
    sign_data = signs_main.get(sign_id)
    extra_data = signs_extra.get(sign_id)
    
    if not sign_data:
        await callback.answer("Знак не знайдено")
        return
    
    # Формуємо детальну інформацію
    name = sign_data["names"].get(study_lang, "")
    text = f"📍 *{name}*\n\n"
    
    if extra_data and "extra" in extra_data:
        extra_text = extra_data["extra"].get(study_lang, "Додаткова інформація недоступна.")
        text += f"{extra_text}\n"
        
        if trans_lang != "none" and trans_lang != study_lang:
            extra_text_trans = extra_data["extra"].get(trans_lang, "")
            if extra_text_trans:
                text += f"\n_{extra_text_trans}_"
    else:
        text += "Додаткова інформація для цього знаку недоступна."
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await message.answer("Спочатку використайте /start")
        return
    
    study_lang_names = {"no": "Норвезька", "en": "Англійська"}
    trans_lang_names = {"no": "Норвезька", "en": "Англійська", "ru": "Російська", "uk": "Українська", "none": "Без перекладу"}
    
    study_lang = study_lang_names.get(user[1], user[1])
    trans_lang = trans_lang_names.get(user[2], user[2])
    learned_count = len(db.get_learned_signs(user_id))
    
    text = (
        f"⚙️ *Налаштування*\n\n"
        f"Мова вивчення: {study_lang}\n"
        f"Мова перекладу: {trans_lang}\n"
        f"Вивчено знаків: {learned_count}/{len(signs_list)}"
    )
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_settings_keyboard())

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
    user_id = callback.from_user.id
    
    db.update_user_theme(user_id, theme)
    
    theme_name = "Світла ☀️" if theme == "light" else "Темна 🌑"
    
    await callback.message.edit_text(
        f"Тему змінено на: {theme_name}\n\n"
        "Поверніться в меню для продовження.",
        reply_markup=None # Можна додати кнопку "Назад" або юзер сам натисне "Налаштування"
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_back")
async def settings_back_callback(callback: CallbackQuery):
    # Повертаємось в головне меню налаштувань.
    # Треба продублювати код з cmd_settings або open_settings_handler, 
    # але оскільки там message, а тут callback, краще винести в окрему функцію generating_settings_text(user)
    
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    study_lang_names = {"no": "Норвезька", "en": "Англійська"}
    trans_lang_names = {"no": "Норвезька", "en": "Англійська", "ru": "Російська", "uk": "Українська", "none": "Без перекладу"}
    
    study_lang = study_lang_names.get(user[1], user[1])
    trans_lang = trans_lang_names.get(user[2], user[2])
    learned_count = len(db.get_learned_signs(user_id))
    
    current_theme = user[3] if len(user) > 3 else 'light' # Індекс може зсунутись
    current_cat = user[4] if len(user) > 4 else 'all'
    
    theme_text = "Світла ☀️" if current_theme == 'light' else "Темна 🌑"
    
    text = (
        f"⚙️ *Налаштування*\n\n"
        f"Мова вивчення: {study_lang}\n"
        f"Мова перекладу: {trans_lang}\n"
        f"Тема: {theme_text}\n"
        f"Категорія: {current_cat}\n"
        f"Виучено знаків: {learned_count}/{len(VALID_SIGNS)}"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_settings_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "change_language")
async def change_language_handler(callback: CallbackQuery, state: FSMContext):
    # Приховуємо reply клавіатуру на час вибору налаштувань (або залишаємо)
    # Оскільки reply клавіатуру не можна просто "приховати" без нового повідомлення,
    # ми просто продовжуємо діалог

    await callback.message.answer(
        "Якою мовою ви плануєте вивчати дорожні знаки?",
        reply_markup=get_language_keyboard()
    )
    await state.set_state(OnboardingStates.choose_study_language)
    await callback.answer()

@dp.callback_query(F.data == "reset_progress")
async def reset_progress_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db.reset_learned_signs(user_id)
    await state.clear()
    
    await callback.message.answer(
        "✅ **Прогрес скинуто!** Всі знаки знову доступні для вивчення.\n\n"
        "Використайте /learn або меню щоб почати спочатку.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.reset_learned_signs(user_id)
    await state.clear()
    
    await message.answer(
        "✅ **Прогрес скинуто!** Всі знаки знову доступні для вивчення.\n\n"
        "Використайте /learn щоб почати спочатку.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )

# ==================== Обробка помилок ====================

@dp.errors()
async def on_error(event: ErrorEvent):
    """Глобальний обробник помилок aiogram.

    Найчастіший кейс — користувач тапає кнопку, що перемальовує повідомлення
    з тим самим текстом/розміткою: Telegram відхиляє no-op редагування з
    `message is not modified`. Це безпечно — просто ігноруємо. Решту помилок
    логуємо з трейсбеком (як і раніше), але позначаємо обробленими, щоб aiogram
    не дублював «scary» необроблений трейсбек і polling не зупинявся.
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
    db.create_tables()
    
    # Виконуємо перевірку картинок при старті
    VALID_SIGNS = validate_signs_integrity(signs_list)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())