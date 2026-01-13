# SPDX-License-Identifier: MIT
# Copyright (c) 2018-2024 Amano LLC
# Copyright (c) 2025 Elinsrc

import asyncio

from hydrogram import Client, filters
from hydrogram.enums import ParseMode, ChatMemberStatus as CMS, ChatType
from hydrogram.errors import BadRequest
from hydrogram.types import (
    ChatPrivileges,
    ChatPermissions,
    InlineKeyboardMarkup, 
    Message, 
    ChatMemberUpdated, 
    InlineKeyboardButton, 
    CallbackQuery,
)

from config import PREFIXES
from miku.database.welcome import get_welcome, set_welcome, toggle_welcome
from miku.utils import button_parser, commands, get_format_keys, check_spam_user, antispam_timeout
from miku.utils.decorators import require_admin, stop_here
from miku.utils.localization import Strings, use_chat_lang
from miku.database.antispam import get_antispam, enable_antispam


VERIFY_CACHE = {}


async def send_welcome_greeting(c: Client, chat_id: int, user, s: Strings):
    welcome, welcome_enabled = await get_welcome(chat_id)
    if not welcome_enabled:
        return

    if welcome is None:
        welcome = s("welcome_default")

    if "count" in get_format_keys(welcome):
        count = await c.get_chat_members_count(chat_id)
    else:
        count = 0

    chat_title = (await c.get_chat(chat_id)).title
    members = [user]

    mention = ", ".join(a.mention for a in members)
    username = ", ".join(f"@{a.username}" if a.username else a.mention for a in members)
    user_id = ", ".join(str(a.id) for a in members)
    full_name = ", ".join(f"{a.first_name} " + (a.last_name or "") for a in members)
    first_name = ", ".join(a.first_name for a in members)

    welcome = welcome.format(
        id=user_id,
        username=username,
        mention=mention,
        first_name=first_name,
        full_name=full_name,
        name=full_name,
        title=chat_title,
        chat_title=chat_title,
        count=count,
    )

    welcome, welcome_buttons = button_parser(welcome)

    await c.send_message(
        chat_id=chat_id,
        text=welcome,
        disable_web_page_preview=True,
        reply_markup=(
            InlineKeyboardMarkup(welcome_buttons) if welcome_buttons else None
        ),
    )


@Client.on_message(filters.command(["welcomeformat", "start welcome_format_help"], PREFIXES))
@use_chat_lang
@stop_here
async def welcome_format_message_help(c: Client, m: Message, s: Strings):
    await m.reply_text(s("welcome_format_help_msg"))


@Client.on_message(filters.command("setwelcome", PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def set_welcome_message(c: Client, m: Message, s: Strings):
    if len(m.text.split()) == 1:
        await m.reply_text(
            s("welcome_set_empty").format(bot_username=c.me.username),
            disable_web_page_preview=True,
        )
        return

    message = m.text.html.split(None, 1)[1]
    try:
        # Try to send message with default parameters
        sent = await m.reply_text(
            message.format(
                id=m.from_user.id,
                username=m.from_user.username,
                mention=m.from_user.mention,
                first_name=m.from_user.first_name,
                full_name=m.from_user.full_name,
                name=m.from_user.first_name,
                # title and chat_title are the same
                title=m.chat.title,
                chat_title=m.chat.title,
                count=(await c.get_chat_members_count(m.chat.id)),
            )
        )
    except (KeyError, BadRequest) as e:
        await m.reply_text(s("welcome_set_error").format(error=f"{e.__class__.__name__}: {e!s}"))

    else:
        await set_welcome(m.chat.id, message)
        await sent.edit_text(s("welcome_set_success").format(chat_title=m.chat.title))


@Client.on_message(
    (filters.command("welcome") & ~filters.command(["welcome on", "welcome off"])) & filters.group
)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def invlaid_welcome_status_arg(c: Client, m: Message, s: Strings):
    await m.reply_text(s("welcome_mode_invalid"))


@Client.on_message(filters.command("getwelcome", PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def getwelcomemsg(c: Client, m: Message, s: Strings):
    welcome, welcome_enabled = await get_welcome(m.chat.id)
    if welcome_enabled:
        await m.reply_text(
            s("welcome_default") if welcome is None else welcome,
            parse_mode=ParseMode.DISABLED,
        )
    else:
        await m.reply_text("None")


@Client.on_message(filters.command("welcome on", PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def enable_welcome_message(c: Client, m: Message, s: Strings):
    await toggle_welcome(m.chat.id, True)
    await m.reply_text(s("welcome_mode_enable").format(chat_title=m.chat.title))


@Client.on_message(filters.command("welcome off", PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def disable_welcome_message(c: Client, m: Message, s: Strings):
    await toggle_welcome(m.chat.id, False)
    await m.reply_text(s("welcome_mode_disable").format(chat_title=m.chat.title))


@Client.on_message(filters.command(["resetwelcome", "clearwelcome"], PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def reset_welcome_message(c: Client, m: Message, s: Strings):
    await set_welcome(m.chat.id, None)
    await m.reply_text(s("welcome_reset").format(chat_title=m.chat.title))


@Client.on_message(
    (filters.command("antispam") & ~filters.command(["antispam on", "antispam off"])) & filters.group
)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def invalid_antispam_status_arg(c: Client, m: Message, s: Strings):
    enabled = await get_antispam(m.chat.id)
    status_text = s("antispam_enable") if enabled else s("antispam_disable")
    await m.reply_text(s("antispam_mode_status").format(status=status_text))


@Client.on_message(filters.command("antispam on", PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def enable_antispam_mode(c: Client, m: Message, s: Strings):
    await enable_antispam(m.chat.id, True)
    await m.reply_text(s("antispam_mode_enable").format(chat_title=m.chat.title))


@Client.on_message(filters.command("antispam off", PREFIXES) & filters.group)
@require_admin(ChatPrivileges(can_change_info=True))
@use_chat_lang
async def disable_antispam_mode(c: Client, m: Message, s: Strings):
    await enable_antispam(m.chat.id, False)
    await m.reply_text(s("antispam_mode_disable").format(chat_title=m.chat.title))


@Client.on_chat_member_updated()
@use_chat_lang
async def greet_new_members(c: Client, m: ChatMemberUpdated, s: Strings):
    if not (
        m.new_chat_member
        and m.new_chat_member.status not in {CMS.RESTRICTED}
        and not m.old_chat_member
    ):
        return

    user = m.new_chat_member.user if m.new_chat_member else m.from_user

    if user.is_bot:
        return

    antispam = await get_antispam(m.chat.id)
    if antispam:
        spam_user = await check_spam_user(user.id)
        if spam_user:
            await c.ban_chat_member(m.chat.id, user.id)

            await c.send_message(
                m.chat.id,
                s("antispam_ban_msg").format(user=user.mention),
            )
            return
        
        if m.chat.type == ChatType.SUPERGROUP:
            await c.restrict_chat_member(
                m.chat.id,
                user.id,
                permissions=ChatPermissions()
                )

            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(s("im_notbot_btn"), callback_data="antispam_verify")]])

            verify_msg = await c.send_message(
                m.chat.id,
                s("antispam_verify_msg").format(user=user.mention),
                reply_markup=keyboard,
            )

            task = asyncio.create_task(antispam_timeout(c, m.chat.id, user.id, verify_msg.id))
            VERIFY_CACHE[user.id] = {
                "task": task,
                "chat_id": m.chat.id,
                "user": user,
                "strings": s,
            }

            return 

    await send_welcome_greeting(c, m.chat.id, user, s)


@Client.on_callback_query(filters.regex("^antispam_verify$"))
@use_chat_lang
async def antispam_verify(c: Client, cb: CallbackQuery, s: Strings):
    user_id = cb.from_user.id
    chat_id = cb.message.chat.id

    await c.restrict_chat_member(
        chat_id,
        user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )

    verify_cache = VERIFY_CACHE.pop(user_id, None)
    if verify_cache and isinstance(verify_cache, dict):
        task = verify_cache.get("task")
        if task:
            task.cancel()
        
        await send_welcome_greeting(
            c,
            verify_cache["chat_id"],
            verify_cache["user"],
            verify_cache["strings"],
        )
    elif verify_cache:
        verify_cache.cancel()

    await cb.message.edit_text(s("antispam_verify_success").format(user=cb.from_user.mention))


commands.add_command("resetwelcome", "admin")
commands.add_command("setwelcome", "admin")
commands.add_command("welcome", "admin")
commands.add_command("welcomeformat", "admin")
commands.add_command("antispam", "admin")
