import json
import os
import sys
from typing import Dict, List, Optional
from io import BytesIO
from PIL import Image

import logging

# Отримуємо абсолютний шлях до папки з ботом
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger(__name__)

# Telegram дозволяє до 10 000 px за сумою ширини й висоти. Квадрат 2048 px
# має великий запас, достатню якість для картки та менше навантажує RAM.
MAX_SIGN_CANVAS_SIZE = 2048

# Оптичний розмір: знаки різної форми мають виглядати однаково «важкими».
# Частка площі квадрата, яку займає сам знак (без прозорого фону):
SIGN_VISUAL_AREA = 0.42
# Межі для довшої сторони знака як частки сторони квадрата.
SIGN_SCALE_MIN, SIGN_SCALE_MAX = 0.6, 0.94
_manifest_cache: Optional[Dict] = None


def cutout_manifest() -> Dict:
    """data/cutouts/manifest.json: форма, заповнення (fill) і пропорції кожного знака."""
    global _manifest_cache
    if _manifest_cache is None:
        try:
            with open(get_path("data/cutouts/manifest.json"), encoding="utf-8") as f:
                _manifest_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _manifest_cache = {}
    return _manifest_cache


def sign_scale(sign_id: str) -> float:
    """Довша сторона знака як частка квадратної картки.

    Площа знака в квадраті зі стороною 1 = d² · min(a, 1/a) · fill, де a — пропорції,
    fill — частка непрозорих пікселів у межах знака (трикутник ~0.5, коло ~0.79,
    прямокутник ~1). Підбираємо d так, щоб площа була однаковою для всіх: трикутник
    і вузький стовпчик стають більшими, квадратна табличка — меншою.
    """
    info = cutout_manifest().get(sign_id)
    if not info or not info.get("fill"):
        return 0.8
    aspect = info.get("aspect") or 1.0
    ratio = min(aspect, 1 / aspect)
    d = (SIGN_VISUAL_AREA / (ratio * info["fill"])) ** 0.5
    return round(min(SIGN_SCALE_MAX, max(SIGN_SCALE_MIN, d)), 3)

def get_path(rel_path: str) -> str:
    """Отримує абсолютний шлях до файлу"""
    return os.path.join(BASE_DIR, rel_path)

def load_signs_main() -> Dict:
    """Завантажує основний JSON з інформацією про знаки"""
    try:
        with open(get_path("data/signs_main.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Помилка: файл {get_path('data/signs_main.json')} не знайдено")
        return {}
    except json.JSONDecodeError:
        print("Помилка: невірний формат JSON в signs_main.json")
        return {}

def load_signs_extra() -> Dict:
    """Завантажує додатковий JSON з детальною інформацією"""
    try:
        with open(get_path("data/signs_extra.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Помилка: файл {get_path('data/signs_extra.json')} не знайдено")
        return {}
    except json.JSONDecodeError:
        print("Помилка: невірний формат JSON в signs_extra.json")
        return {}

def load_signs_list() -> List[str]:
    """Завантажує список ID знаків"""
    try:
        with open(get_path("data/signs_list.txt"), "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Помилка: файл {get_path('data/signs_list.txt')} не знайдено")
        return []

def find_sign_image(sign_id: str) -> Optional[str]:
    """
    Шукає картинку знаку: спершу вирізаний знак без фону (data/cutouts/*.webp,
    готує tools/cutout.py), потім оригінал у data/images/.
    """
    cutout = get_path(os.path.join("data", "cutouts", f"{sign_id}.webp"))
    if os.path.exists(cutout):
        return cutout

    image_dir = get_path("data/images")
    for ext in (".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"):
        image_path = os.path.join(image_dir, f"{sign_id}{ext}")
        if os.path.exists(image_path):
            return image_path
    return None

def validate_signs_integrity(signs_list: List[str]) -> List[str]:
    """
    Перевіряє наявність зображень для всіх знаків у списку.
    Логує помилки для відсутніх файлів.
    Повертає список тільки валідних ID (для яких є фото).
    """
    valid_signs = []
    missing_signs = []
    
    print("🔄 Запуск перевірки цілісності бази знаків...")
    
    for sign_id in signs_list:
        image_path = find_sign_image(sign_id)
        if image_path:
            # Спробуємо відкрити файл, щоб переконатися, що він не битий
            try:
                with Image.open(image_path) as img:
                    img.verify()
                valid_signs.append(sign_id)
            except Exception as e:
                logger.error(f"❌ Пошкоджений файл зображення для знаку {sign_id} ({image_path}): {e}")
                missing_signs.append(sign_id)
        else:
            logger.warning(f"⚠️ Відсутнє зображення для знаку: {sign_id}")
            missing_signs.append(sign_id)
            
    if missing_signs:
        logger.info(f"🚫 Знайдено {len(missing_signs)} проблемних знаків. Вони будуть виключені з вивчення.")
    else:
        logger.info("✅ Всі знаки мають коректні зображення.")
        
    return valid_signs

def process_sign_image(image_path: str, theme: str = 'light',
                       scale: Optional[float] = None) -> Optional[BytesIO]:
    """
    Обробляє зображення: розміщує його на білому (або темному) квадратному фоні.
    scale — довша сторона знака як частка сторони квадрата (sign_scale);
    за замовчуванням береться з маніфесту за назвою файлу.
    Повертає об'єкт BytesIO з готовим зображенням.
    """
    if scale is None:
        scale = sign_scale(os.path.splitext(os.path.basename(image_path))[0])
    try:
        with Image.open(image_path) as img:
            # Конвертуємо в RGBA для коректної обробки прозорості
            img = img.convert("RGBA")

            # Визначаємо розміри
            w, h = img.size
            max_dim = max(w, h)

            # Великі вихідні JPEG раніше давали квадрати >5000 px,
            # які Telegram відхиляв з PHOTO_INVALID_DIMENSIONS.
            max_content_size = int(MAX_SIGN_CANVAS_SIZE * scale)
            if max_dim > max_content_size:
                shrink = max_content_size / max_dim
                resized = (
                    max(1, round(w * shrink)),
                    max(1, round(h * shrink)),
                )
                img = img.resize(resized, Image.Resampling.LANCZOS)
                w, h = img.size
                max_dim = max(w, h)

            canvas_size = max(max_dim + 2, round(max_dim / scale))

            # Визначаємо колір фону залежно від теми
            if theme == 'dark':
                bg_color = (43, 43, 43)  # Темно-сірий (Dark Grey)
            else:
                bg_color = (255, 255, 255)  # Білий

            # Створюємо фон
            bg = Image.new('RGB', (canvas_size, canvas_size), bg_color)

            # Центруємо зображення
            pos = ((canvas_size - w) // 2, (canvas_size - h) // 2)
            bg.paste(img, pos, mask=img)

            # Зберігаємо в буфер
            output = BytesIO()
            bg.save(output, format='JPEG', quality=92, optimize=True)
            output.seek(0)
            return output
    except Exception as e:
        logger.error(f"Помилка обробки зображення {image_path}: {e}")
        return None
