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
    Шукає файл картинки для знаку в папці data/images/
    Підтримує формати .png та .jpg/.jpeg
    """
    image_dir = get_path("data/images")
    
    # Перевіряємо різні можливі розширення
    extensions = [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"]
    
    for ext in extensions:
        image_path = os.path.join(image_dir, f"{sign_id}{ext}")
        if os.path.exists(image_path):
            return image_path
    
    # Якщо файл не знайдено
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

def process_sign_image(image_path: str, theme: str = 'light') -> Optional[BytesIO]:
    """
    Обробляє зображення: розміщує його на білому (або темному) квадратному фоні.
    Повертає об'єкт BytesIO з готовим зображенням.
    """
    try:
        with Image.open(image_path) as img:
            # Конвертуємо в RGBA для коректної обробки прозорості
            img = img.convert("RGBA")
            
            # Визначаємо розміри
            w, h = img.size
            max_dim = max(w, h)
            
            # Додаємо невеликий відступ (наприклад 5% від розміру)
            padding = int(max_dim * 0.05)
            canvas_size = max_dim + (padding * 2)
            
            # Визначаємо колір фону залежно від теми
            if theme == 'dark':
                bg_color = (43, 43, 43) # Темно-сірий (Dark Grey)
            else:
                bg_color = (255, 255, 255) # Білий
            
            # Створюємо фон
            bg = Image.new('RGB', (canvas_size, canvas_size), bg_color)
            
            # Центруємо зображення
            pos = ((canvas_size - w) // 2, (canvas_size - h) // 2)
            bg.paste(img, pos, mask=img)
            
            # Зберігаємо в буфер
            output = BytesIO()
            bg.save(output, format='JPEG', quality=95)
            output.seek(0)
            return output
    except Exception as e:
        logger.error(f"Помилка обробки зображення {image_path}: {e}")
        return None