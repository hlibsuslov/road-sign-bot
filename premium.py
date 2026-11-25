"""Premium: a Telegram Stars subscription (default 50 Stars per 30 days).

Flow (references: telegram-bot-ui recipe 25, core.telegram.org/bots/payments-stars):
  1. Paywall screen or the Mini App asks for an invoice link (createInvoiceLink with
     subscription_period = 30 days, currency XTR, one price item).
  2. pre_checkout_query: re-check payload, currency and amount on the server, refuse a
     second concurrent subscription, answer within 10 s. Nothing is granted here.
  3. successful_payment (first payment and every renewal): stored once per
     telegram_payment_charge_id; the access period comes from subscription_expiration_date.
  4. Cancel / resume renewal from the bot: editUserStarSubscription; access stays until
     the end of the paid period.

The paywall is off unless PAYWALL_ENABLED=1, so deploying this code changes nothing
for users until the owner switches it on (test bot first).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

logger = logging.getLogger(__name__)

PERIOD_SECONDS = 2592000          # the only period Telegram allows for Stars subscriptions
GRACE_SECONDS = 6 * 3600          # a renewal can arrive a little after the period ends
PAYLOAD_PREFIX = "premium:"

BTN_PREMIUM = "⭐ Преміум"
FEATURES = (
    "навчання і тести в застосунку «Знаки»",
    "режим іспиту з таймером і розбором помилок",
    "повна статистика прогресу",
)

router = Router(name="premium")


def price_stars() -> int:
    return int(os.getenv("PREMIUM_STARS", "50"))


def paywall_enabled() -> bool:
    return os.getenv("PAYWALL_ENABLED") == "1"


def is_premium(db, user_id: int, now: int | None = None) -> bool:
    """Single entitlement check for the bot and the Mini App."""
    if not paywall_enabled():
        return True
    sub = db.get_subscription(user_id)
    now = int(time.time()) if now is None else now
    return bool(sub) and sub["expires_at"] + GRACE_SECONDS > now


def status(db, user_id: int) -> dict:
    sub = db.get_subscription(user_id)
    now = int(time.time())
    active = bool(sub) and sub["expires_at"] + GRACE_SECONDS > now
    return {
        "paywall": paywall_enabled(),
        "premium": is_premium(db, user_id, now),
        "active": active,
        "expires_at": sub["expires_at"] if sub else None,
        "renews": active and not sub["is_canceled"],
        "price": price_stars(),
    }


def payload_for(user_id: int) -> str:
    return f"{PAYLOAD_PREFIX}{user_id}"


async def invoice_link(bot: Bot, user_id: int) -> str:
    stars = price_stars()
    return await bot.create_invoice_link(
        title="Преміум на 30 днів",
        description="Навчання і тести в застосунку «Знаки», режим іспиту, повна статистика. "
                    "Продовжується щомісяця, скасувати можна будь-коли.",
        payload=payload_for(user_id),
        currency="XTR",
        prices=[LabeledPrice(label="Преміум, 30 днів", amount=stars)],
        subscription_period=PERIOD_SECONDS,
    )


def check_pre_checkout(db, user_id: int, payload: str, currency: str, amount: int) -> str | None:
    """None = accept; otherwise the reason shown to the user. Grants nothing."""
    if payload != payload_for(user_id):
        return "Цей рахунок створено для іншого акаунта."
    if currency != "XTR" or amount != price_stars():
        return "Ціна змінилася. Відкрийте /premium і оформіть ще раз."
    st = status(db, user_id)
    if st["active"] and st["renews"]:
        return "Преміум уже активний — друга підписка не потрібна."
    return None


def apply_payment(db, user_id: int, pay) -> int | None:
    """Store a successful_payment once and extend access. Returns the new expiry, or None
    when the payment is not ours or was already applied (redelivered update)."""
    if pay.invoice_payload != payload_for(user_id) or pay.currency != "XTR":
        logger.error("Payment with unexpected payload/currency, charge %s", pay.telegram_payment_charge_id)
        return None
    expires = pay.subscription_expiration_date or int(time.time()) + PERIOD_SECONDS
    try:
        fresh = db.apply_subscription_payment(
            charge_id=pay.telegram_payment_charge_id, user_id=user_id,
            amount=pay.total_amount, currency=pay.currency, payload=pay.invoice_payload,
            expires_at=expires, is_recurring=bool(pay.is_recurring),
            is_first_recurring=bool(pay.is_first_recurring),
        )
    except Exception:
        # Polling won't redeliver this update: the charge id is what support needs to restore access.
        logger.exception("PAYMENT NOT APPLIED: user %s charge %s", user_id, pay.telegram_payment_charge_id)
        raise
    return expires if fresh else None


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")


# ---------------------------------------------------------------- screens

def screen(db, user_id: int, link: str | None) -> tuple[str, InlineKeyboardMarkup | None]:
    st = status(db, user_id)
    stars = st["price"]
    features = "\n".join(f"• {escape(f)}" for f in FEATURES)
    if st["active"] and st["renews"]:
        return (f"⭐ <b>Преміум активний</b>\n\nНаступне продовження — {_date(st['expires_at'])}, "
                f"{stars} ⭐.\n\n{features}",
                InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text="Скасувати продовження", callback_data="premium_cancel")]]))
    if st["active"]:
        return (f"⭐ <b>Преміум до {_date(st['expires_at'])}</b>\n\n"
                "Продовження вимкнено: доступ залишиться до кінця оплаченого місяця.",
                InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text="Відновити продовження", callback_data="premium_resume", style="primary")]]))
    text = (f"⭐ <b>Преміум</b>\n\n{features}\n\n"
            f"<b>{stars} ⭐ на місяць.</b> Скасувати можна будь-коли, доступ залишиться до кінця місяця.")
    if not st["paywall"]:
        text += "\n\nЗараз усе доступно безкоштовно."
        return text, None
    if not link:
        return text + "\n\nНе вдалося створити рахунок. Спробуйте ще раз за хвилину.", None
    return text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"Оформити · {stars} ⭐ на місяць", url=link, style="primary")]])


async def show(message: Message, db, user_id: int, bot: Bot, *, edit: bool = False):
    link = None
    if paywall_enabled() and not status(db, user_id)["active"]:
        try:
            link = await invoice_link(bot, user_id)
        except Exception as exc:  # logged; the screen explains and offers no dead button
            logger.warning("createInvoiceLink failed: %s", exc)
    text, kb = screen(db, user_id, link)
    if edit:
        await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------- handlers

def setup(db):
    """Bind handlers to the bot's database. Include `router` before any catch-all router."""

    @router.message(Command("premium"))
    async def cmd_premium(message: Message, bot: Bot):
        if db.get_user(message.from_user.id) is None:
            await message.answer("Спочатку відкрийте /start.")
            return
        await show(message, db, message.from_user.id, bot)

    @router.callback_query(F.data == "premium_open")
    async def open_premium(callback: CallbackQuery, bot: Bot):
        await callback.answer()
        await show(callback.message, db, callback.from_user.id, bot)

    @router.callback_query(F.data.in_({"premium_cancel", "premium_resume"}))
    async def toggle_renewal(callback: CallbackQuery, bot: Bot):
        cancel = callback.data == "premium_cancel"
        sub = db.get_subscription(callback.from_user.id)
        if not sub or sub["expires_at"] + GRACE_SECONDS <= int(time.time()):
            await callback.answer("Підписка вже неактивна.", show_alert=True)
            return
        try:
            await bot.edit_user_star_subscription(
                user_id=callback.from_user.id,
                telegram_payment_charge_id=sub["charge_id"],
                is_canceled=cancel,
            )
        except Exception as exc:
            logger.warning("editUserStarSubscription failed: %s", exc)
            await callback.answer("Не вдалося змінити підписку. Спробуйте пізніше.", show_alert=True)
            return
        db.set_subscription_canceled(callback.from_user.id, cancel)
        await callback.answer("Продовження вимкнено" if cancel else "Продовження увімкнено")
        await show(callback.message, db, callback.from_user.id, bot, edit=True)

    @router.pre_checkout_query()
    async def pre_checkout(query: PreCheckoutQuery):
        reason = check_pre_checkout(db, query.from_user.id, query.invoice_payload,
                                    query.currency, query.total_amount)
        if reason:
            await query.answer(ok=False, error_message=reason)
        else:
            await query.answer(ok=True)

    @router.message(F.successful_payment)
    async def on_payment(message: Message):
        pay = message.successful_payment
        expires = apply_payment(db, message.from_user.id, pay)
        if expires is None:
            return
        if pay.is_recurring and not pay.is_first_recurring:
            await message.answer(f"⭐ Преміум продовжено до {_date(expires)}.")
        else:
            await message.answer(
                f"⭐ <b>Дякуємо! Преміум активний до {_date(expires)}.</b>\n\n"
                "Навчання і тести — у кнопці «Знаки» внизу чату.",
                parse_mode=ParseMode.HTML,
            )

    @router.message(F.refunded_payment)
    async def on_refund(message: Message):
        refund = message.refunded_payment
        if db.apply_refund(message.from_user.id, refund.telegram_payment_charge_id):
            await message.answer("Кошти повернено. Преміум вимкнено.")

    @router.message(Command("paysupport"))
    async def paysupport(message: Message):
        contact = os.getenv("SUPPORT_CONTACT")
        text = ("<b>Допомога з оплатою</b>\n\nОпишіть, що сталося, і додайте дату платежу. "
                "Скасувати продовження — /premium.")
        if contact:
            text += f"\nНапишіть: {escape(contact)}"
        await message.answer(text, parse_mode=ParseMode.HTML)

    @router.message(Command("terms"))
    async def terms(message: Message):
        await message.answer(
            "<b>Умови</b>\n\nПреміум — цифрова послуга на 30 днів за Telegram Stars, "
            "продовжується автоматично. Скасувати продовження можна будь-коли в /premium; "
            "доступ зберігається до кінця оплаченого періоду. Питання щодо оплати — /paysupport.",
            parse_mode=ParseMode.HTML,
        )

    return router
