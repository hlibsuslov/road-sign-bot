"""Методика навчання: активне пригадування + інтервальні повторення (Лейтнер).

Кожен знак проходить шлях:
  1. Знайомство — картка зі знаком, назвою та описом (box 0).
  2. Перевірки — квіз «що означає цей знак?» з 4 варіантами відповіді.
     Правильна відповідь піднімає знак на рівень вище, інтервал до наступного
     повторення зростає. Помилка скидає знак на початок із швидким повтором.
  3. Вивчено — знак досяг рівня MASTERED_BOX, але зрідка повторюється далі.

Наступний крок завжди обирається за пріоритетом:
  прострочені повторення (найстаріші першими) -> нові знаки.
"""

import random
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

MAX_BOX = 6
MASTERED_BOX = 4

# Інтервал до наступного повторення після досягнення рівня (box -> секунди)
INTERVALS = {
    1: 30 * 60,        # 30 хвилин
    2: 1 * 86400,      # 1 день
    3: 3 * 86400,      # 3 дні
    4: 7 * 86400,      # 7 днів  (з цього рівня знак вважається вивченим)
    5: 14 * 86400,     # 14 днів
    6: 30 * 86400,     # 30 днів
}

INTRO_DELAY = 3 * 60   # перший квіз — за ~3 хв після знайомства (інтерлівінг)
RETRY_DELAY = 3 * 60   # швидкий повтор після помилки


def schedule_after_intro(now: int) -> tuple:
    """(box, next_review_at) для щойно показаного знаку."""
    return 0, now + INTRO_DELAY


def schedule_after_answer(box: int, correct: bool, now: int) -> tuple:
    """(новий box, next_review_at) після відповіді у квізі."""
    if correct:
        new_box = min(box + 1, MAX_BOX)
        return new_box, now + INTERVALS[new_box]
    return 0, now + RETRY_DELAY


def schedule_known(now: int) -> tuple:
    """(box, next_review_at) для «вже знаю цей знак»."""
    return MASTERED_BOX, now + INTERVALS[MASTERED_BOX]


def pick_next(pool: List[str], progress_map: Dict, now: Optional[int] = None) -> tuple:
    """Обирає наступний крок навчання.

    Повертає (sign_id, mode), де mode:
      'review' — квіз на повторення (настав час),
      'new'    — знайомство з новим знаком,
      None     — зараз нічого робити (все повторено, нових немає).
    """
    now = now or int(time.time())
    pool_set = set(pool)

    due = [
        p for s_id, p in progress_map.items()
        if s_id in pool_set and p["next_review_at"] <= now
    ]
    if due:
        due.sort(key=lambda p: p["next_review_at"])
        return due[0]["sign_id"], "review"

    new_signs = [s for s in pool if s not in progress_map]
    if new_signs:
        return random.choice(new_signs), "new"

    return None, None


def earliest_due(pool: List[str], progress_map: Dict) -> Optional[Dict]:
    """Найближчий до повторення знак у пулі (для дострокового повторення)."""
    pool_set = set(pool)
    rows = [p for s_id, p in progress_map.items() if s_id in pool_set]
    if not rows:
        return None
    return min(rows, key=lambda p: p["next_review_at"])


def build_quiz_options(sign_id: str, signs_main: Dict, valid_signs: List[str],
                       study_lang: str, n_options: int = 4) -> List[str]:
    """4 варіанти відповіді: правильний + дистрактори (бажано з тієї ж категорії).

    Дистрактори з назвою, що збігається з правильною (варіанти одного знаку),
    відсіюються, щоб питання не мало двох правильних відповідей.
    """
    sign = signs_main[sign_id]
    correct_name = sign["names"].get(study_lang, "")
    category = sign.get("category_code")

    def usable(s_id: str) -> bool:
        if s_id == sign_id:
            return False
        data = signs_main.get(s_id)
        return bool(data) and data["names"].get(study_lang, "") not in ("", correct_name)

    same_cat = [s for s in valid_signs
                if usable(s) and signs_main[s].get("category_code") == category]
    other = [s for s in valid_signs
             if usable(s) and signs_main[s].get("category_code") != category]

    random.shuffle(same_cat)
    random.shuffle(other)

    distractors, seen_names = [], {correct_name}
    for s_id in same_cat + other:
        name = signs_main[s_id]["names"].get(study_lang, "")
        if name in seen_names:
            continue
        distractors.append(s_id)
        seen_names.add(name)
        if len(distractors) >= n_options - 1:
            break

    options = distractors + [sign_id]
    random.shuffle(options)
    return options


def count_streak(active_days: List[str]) -> int:
    """Серія днів поспіль із активністю. active_days — ISO-дати, нові першими.

    Серія не обнуляється, якщо сьогодні ще не займався, але вчора займався.
    """
    if not active_days:
        return 0
    today = date.today()
    last = date.fromisoformat(active_days[0])
    if (today - last).days > 1:
        return 0
    streak, prev = 1, last
    for day_str in active_days[1:]:
        day = date.fromisoformat(day_str)
        if (prev - day).days == 1:
            streak += 1
            prev = day
        else:
            break
    return streak


def humanize_seconds(seconds: int) -> str:
    """Інтервал часу людською мовою: '2 дн', '3 год 15 хв', '5 хв'."""
    if seconds < 60:
        return "менше хвилини"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} хв"
    hours = minutes // 60
    if hours < 24:
        rest_min = minutes % 60
        return f"{hours} год {rest_min} хв" if rest_min else f"{hours} год"
    days = hours // 24
    rest_h = hours % 24
    return f"{days} дн {rest_h} год" if rest_h else f"{days} дн"


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "▱" * width
    filled = round(width * done / total)
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)
