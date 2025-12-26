# SPDX-License-Identifier: MIT
# Copyright (c) 2018-2024 Amano LLC

from hydrogram import Client
from hydrogram.types import Message

from miku.database.chats import add_chat, chat_exists
from miku.database.antispam import get_antispam
from miku.utils.localization import Strings, use_chat_lang
from miku.utils import check_spam_user

# This is the first plugin run to guarantee
# that the actual chat is initialized in the DB.


@Client.on_message(group=-1)
@use_chat_lang
async def check_chat(c: Client, m: Message, s: Strings):
    if not m.from_user:
        return

    chatexists = await chat_exists(m.chat.id, m.chat.type)

    if not chatexists:
        await add_chat(m.chat.id, m.chat.type)

    antispam = await get_antispam(m.chat.id)
    if antispam:
        spam_user = await check_spam_user(m.from_user.id)
        if spam_user:
            await c.ban_chat_member(m.chat.id, m.from_user.id)
            await c.delete_user_history(m.chat.id, m.from_user.id)
            await c.send_message(m.chat.id, s("antispam_ban_msg").format(user=m.from_user.mention))
