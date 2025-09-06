# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Elinsrc

from hydrogram import Client, filters
from hydrogram.types import CallbackQuery
from hydrogram.enums import ChatType

import logging

logging.basicConfig(level=logging.INFO)

@Client.on_callback_query(filters.regex(r"^delete_message$"))
async def delete_message(c: Client, query: CallbackQuery):
    try:
        if query.message.chat.type == ChatType.PRIVATE:
            await query.message.delete()
        else:
            await query.message.delete()
            await query.message.reply_to_message.delete()
    except Exception as e:
        logging.error(e)
