# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Elinsrc

import asyncio
import re
from loguru import logger

from hydrogram import Client, filters
from hydrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from config import PREFIXES
from miku.utils import commands, inline_commands
from miku.utils.localization import Strings, use_chat_lang
from miku.utils.xashlib import ms_list, remove_color_tags, get_servers, query_servers


class ServerManager:
    def __init__(self):
        self.servers_map = {}

    async def build_server_keyboard(self, user_id: int, mid: int, page: int):
        servers_list = self.servers_map.get((user_id, mid), [])
        keyboard = []

        servers_per_page = 10
        start_index = page * servers_per_page
        end_index = start_index + servers_per_page
        total_servers = len(servers_list)
        page_count = (total_servers + servers_per_page - 1) // servers_per_page

        for i in range(start_index, min(end_index, total_servers)):
            hostname, _, players, maxplayers, _ = servers_list[i]
            keyboard.append([InlineKeyboardButton(
                f"{hostname} ({players}/{maxplayers})",
                callback_data=f"server_info_{user_id}_{mid}_{i}"
            )])

        nav_buttons = []
        if start_index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{user_id}_{mid}_{page - 1}"))
        else:
            nav_buttons.append(InlineKeyboardButton("⏺️", callback_data="ignore"))

        nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data="ignore"))

        if end_index < total_servers:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{user_id}_{mid}_{page + 1}"))
        else:
            nav_buttons.append(InlineKeyboardButton("⏺️", callback_data="ignore"))

        keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("🗑️", callback_data="delete_server_menu")])

        return InlineKeyboardMarkup(keyboard)

    async def get_servers_info(self, gamedir, s):
        self.servers_list = []
        servers = {"servers": []}
        ip_list = await get_servers(gamedir, 0, ms_list[0], 0.5)

        if ip_list:
            coros = [query_servers(ip, servers, 0.5) for ip in ip_list]
            await asyncio.gather(*coros)

        for i in servers["servers"]:
            if i['host'] is None:
                continue
            server_info = (
                f"{s('xash_server')} {remove_color_tags(i['host'])}\n"
                f"{s('xash_map')} {i['map']} ({i['numcl']}/{i['maxcl']})\n"
            )
            if i['players_list']:
                server_info += f"\n{s('xash_players')}\n"
                for index, player_info in i['players_list'].items():
                    server_info += f"{index} {remove_color_tags(player_info[0])} [{player_info[1]}] ({player_info[2]})\n"
                server_info += "\n"
            server_info += (
                f"IP: {i['addr']}:{i['port']}\n"
                f"{s('xash_protocol')}{i['protocol_ver']}, Xash3D FWGS {0.21 if i['protocol_ver'] == 49 else 0.19}\n"
            )
            self.servers_list.append((remove_color_tags(i['host']), i['map'], i['numcl'], i['maxcl'], server_info))


server_manager = ServerManager()


@Client.on_message(filters.command("xash", PREFIXES))
@use_chat_lang
async def xash_chat(c: Client, m: Message, s: Strings):
    user_id = m.from_user.id
    parts = m.text.split(maxsplit=1)

    if len(parts) == 1:
        await m.reply_text(s("xash_example"))
        return

    gamedir = parts[1]
    await server_manager.get_servers_info(gamedir, s)

    if server_manager.servers_list:
        mid = m.id
        server_manager.servers_map[(user_id, mid)] = server_manager.servers_list
        keyboard = await server_manager.build_server_keyboard(user_id, mid, 0)
        await m.reply_text(
            s("xash_select_server").format(count=len(server_manager.servers_list)),
            reply_markup=keyboard
        )


@Client.on_inline_query(filters.regex(r"^(xash) .+", re.IGNORECASE))
@use_chat_lang
async def xash_inline(c: Client, m: InlineQuery, s: Strings):
    text = m.query
    parts = text.split(maxsplit=1)

    if len(parts) == 1:
        await m.answer([
            InlineQueryResultArticle(
                title=s("xash_example"),
                input_message_content=InputTextMessageContent(message_text=s("xash_example")),
            )
        ], cache_time=0)
        return

    gamedir = parts[1]
    temp_manager = ServerManager()
    await temp_manager.get_servers_info(gamedir, s)

    results = []
    for hostname, map_name, players, maxplayers, info in temp_manager.servers_list:
        results.append(InlineQueryResultArticle(
            title=hostname,
            input_message_content=InputTextMessageContent(message_text=info),
            description=f"{map_name} ({players}/{maxplayers})"
        ))

    await m.answer(results, cache_time=0)
    del temp_manager


@Client.on_callback_query(filters.regex(r"^page_"))
async def handle_pagination(c: Client, query: CallbackQuery):
    _, user_id, mid, page = query.data.split("_")
    user_id, mid, page = int(user_id), int(mid), int(page)
    keyboard = await server_manager.build_server_keyboard(user_id, mid, page)
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=keyboard)


@Client.on_callback_query(filters.regex(r"^server_info_"))
async def handle_server_info(c: Client, query: CallbackQuery):
    _, _, user_id, mid, index = query.data.split("_")
    user_id, mid, index = int(user_id), int(mid), int(index)
    servers_list = server_manager.servers_map.get((user_id, mid), [])
    if index < len(servers_list):
        server_info = servers_list[index][-1]
        await query.message.edit_text(server_info)
    else:
        await query.answer("Invalid server index.")


@Client.on_callback_query(filters.regex(r"^delete_server_menu$"))
async def delete_server_menu(c: Client, query: CallbackQuery):
    try:
        mid = query.message.id

        await query.message.delete()

        if query.message.reply_to_message:
            await query.message.reply_to_message.delete()

        keys_to_delete = [key for key in server_manager.servers_map if key[1] == mid]
        for key in keys_to_delete:
            del server_manager.servers_map[key]

    except Exception as e:
        logger.error(e)


commands.add_command("xash", "info")
inline_commands.add_command("xash <game folder>")
