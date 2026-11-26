"""One premium emoji family for the whole bot, with a Unicode fallback for every icon.

Telegram shows custom emoji from a bot only if the bot owns a Fragment username or its
owner has Telegram Premium (private chats). It never returns an error otherwise, it just
strips them. So:
  * CUSTOM_EMOJI=1 is the owner's statement of eligibility; without it nothing changes.
  * Ids are never written by hand: at startup the bot reads the packs with getStickerSet
    (PREMIUM_EMOJI_PACKS, default the static iOS/macOS interface glyphs tgmacicons with its
    sibling tgiosicons) and maps each slot to the first sticker whose `emoji` matches one of
    the slot's meanings. Unresolved slots stay Unicode, and the coverage is logged.
  * Every icon keeps its Unicode character: inside <tg-emoji> in texts, and buttons keep a
    readable label if the icon is dropped.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from html import escape

logger = logging.getLogger(__name__)

# slot -> Unicode meanings, most specific first. The first one is the fallback character.
SLOTS: dict[str, tuple[str, ...]] = {
    "home": ("🏠", "🏡"),
    "back": ("⬅️", "◀️", "🔙", "↩️"),
    "next": ("➡️", "▶️"),
    "study": ("🎓", "📖", "📚"),
    "theory": ("📚", "📖", "📓"),
    "app": ("📱", "📲", "💻"),
    "stats": ("📊", "📈"),
    "categories": ("📂", "🗂", "📁"),
    "settings": ("⚙️", "🛠"),
    "premium": ("⭐️", "⭐", "🌟"),
    "language": ("🌐", "🌍"),
    "theme": ("🎨", "🌓", "🌙"),
    "data": ("📄", "🧾", "📋"),
    "trash": ("🗑", "❌"),
    "selected": ("✅", "☑️", "✔️"),
    "unselected": ("⚪️", "⚪", "⭕️", "⬜️"),
    "correct": ("✅", "✔️"),
    "wrong": ("❌", "✖️"),
    "info": ("ℹ️", "💡"),
    "repeat": ("🔁", "🔄"),
    "target": ("🎯",),
    "streak": ("🔥", "⚡"),
    "calendar": ("📅", "🗓"),
    "done": ("🏁", "🏆", "🎉"),
    "question": ("❓", "❔"),
    "known": ("👍", "👌"),
}

DEFAULT_PACKS = "tgmacicons,tgiosicons"


def _key(e: str) -> str:
    """Compare emoji without variation selectors (⭐ == ⭐️)."""
    return e.replace("️", "").replace("︎", "")


@dataclass
class _State:
    ids: dict[str, str]                 # any custom emoji: used inside message texts
    static_ids: dict[str, str] = None   # static only: the only ones allowed on buttons


_state = _State(ids={}, static_ids={})


def enabled() -> bool:
    return os.getenv("CUSTOM_EMOJI") == "1"


def char(slot: str) -> str:
    return SLOTS[slot][0]


def emoji_id(slot: str) -> str | None:
    return _state.ids.get(slot) if enabled() else None


def tg(slot: str) -> str:
    """Icon inside an HTML message: the custom emoji if resolved, the Unicode char otherwise."""
    cid = emoji_id(slot)
    if cid:
        return f'<tg-emoji emoji-id="{escape(cid)}">{char(slot)}</tg-emoji>'
    return char(slot)


def label(slot: str, text: str) -> tuple[str, str | None]:
    """(button text, icon_custom_emoji_id). Buttons never get an animated emoji: only a slot
    resolved from a static pack becomes an icon; otherwise the Unicode character stays."""
    cid = (_state.static_ids or {}).get(slot) if enabled() else None
    return (text, cid) if cid else (f"{char(slot)} {text}", None)


def is_static(sticker) -> bool:
    return not (sticker.is_animated or sticker.is_video)


def resolve_from_sets(sets: list, static_only: bool = False) -> dict[str, str]:
    """slot -> custom_emoji_id from getStickerSet results (static stickers preferred)."""
    by_emoji: dict[str, str] = {}
    for sticker_set in sets:
        stickers = [s for s in sticker_set.stickers if is_static(s)] if static_only else sticker_set.stickers
        for st in sorted(stickers, key=lambda s: not is_static(s)):
            if st.custom_emoji_id and st.emoji:
                by_emoji.setdefault(_key(st.emoji), st.custom_emoji_id)
    found = {}
    for slot, meanings in SLOTS.items():
        for m in meanings:
            if _key(m) in by_emoji:
                found[slot] = by_emoji[_key(m)]
                break
    return found


async def load(bot) -> None:
    """Read the packs once at startup. Failures leave every icon on Unicode."""
    if not enabled():
        logger.info("Premium emoji: off (CUSTOM_EMOJI is not 1)")
        return
    sets = []
    for name in [n.strip() for n in os.getenv("PREMIUM_EMOJI_PACKS", DEFAULT_PACKS).split(",") if n.strip()]:
        try:
            sets.append(await bot.get_sticker_set(name=name))
        except Exception as exc:
            logger.warning("Premium emoji: pack %s not loaded (%s)", name, exc)
    _state.ids = resolve_from_sets(sets)
    button_sets = []
    for name in [n.strip() for n in os.getenv("PREMIUM_EMOJI_BUTTON_PACKS", "").split(",") if n.strip()]:
        try:
            button_sets.append(await bot.get_sticker_set(name=name))
        except Exception as exc:
            logger.warning("Premium emoji: button pack %s not loaded (%s)", name, exc)
    _state.static_ids = resolve_from_sets(sets + button_sets, static_only=True)
    missing = sorted(set(SLOTS) - set(_state.ids))
    logger.info("Premium emoji: %s of %s slots in texts, %s static for buttons; Unicode for %s",
                len(_state.ids), len(SLOTS), len(_state.static_ids), ", ".join(missing) or "none")
