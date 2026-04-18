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

from config import PREFIXES, STEAM_API_KEY, IGNORE_SERVERS
from miku.utils import commands, inline_commands
from miku.utils.localization import Strings, use_chat_lang
from miku.utils.query import XashServerQuery, GoldSrcServerQuery

# Telegram allow max 50 inline results
MAX_INLINE_RESULTS = 50

class ServerManager:
    def __init__(self):
        self.servers_map = {}

    async def build_server_keyboard(self, user_id: int, mid: int, page: int) -> InlineKeyboardMarkup:
        servers_list = self.servers_map.get((user_id, mid), [])
        keyboard = []

        servers_per_page = 10
        start_index = page * servers_per_page
        end_index = start_index + servers_per_page
        total_servers = len(servers_list)
        page_count = max(1, (total_servers + servers_per_page - 1) // servers_per_page)

        for i in range(start_index, min(end_index, total_servers)):
            hostname, _, players, maxplayers, _ = servers_list[i]
            keyboard.append([
                InlineKeyboardButton(
                    f"{hostname} ({players}/{maxplayers})",
                    callback_data=f"server_info_{user_id}_{mid}_{i}",
                )
            ])

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

    async def _query_single_server(self, querier, ip: str, port: int, s: Strings, results: list) -> None:
        try:
            port = int(port)
            info = await querier.query(ip, port)
            if not info:
                return
            
            if any(x.lower() in info["host"].lower() for x in IGNORE_SERVERS):
                return

            num_players = int(info["numcl"]) if str(info["numcl"]).isdigit() else 0

            players_list = await querier.get_players(ip, port)

            # Ignore empty servers if players list is not available (could be due to query failure)
            if num_players > 0 and not players_list:
                return

            engine_label = (
                s("xash3d_server") if info["engine"] == "xash3d" else s("goldsrc_server")
            )
            server_info = (
                f"{engine_label} {info['host']}\n"
                f"{s('game_map')} {info['map']} "
                f"({info['numcl']}/{info['maxcl']})\n"
            )

            if players_list:
                server_info += f"\n{s('game_players')}\n"
                for idx, player_data in players_list.items():
                    server_info += (
                        f"{idx} {player_data[0]} [{player_data[1]}] ({player_data[2]})\n"
                    )
                server_info += "\n"

            server_info += f"IP: {info['addr']}:{info['port']}\n"

            results.append((
                info["host"],
                info["map"],
                info["numcl"],
                info["maxcl"],
                server_info,
            ))
        except Exception as e:
            logger.warning(f"Failed to query {ip}:{port} — {e}")

    async def get_servers_info(self, engine: str, gamedir: str, s: Strings) -> list:
        results = []

        if engine == "xash3d":
            querier = XashServerQuery()
        else:
            querier = GoldSrcServerQuery(steam_api_key=STEAM_API_KEY)

        ip_list = await querier.get_server_list(gamedir)
        if not ip_list:
            return results
        
        ip_list = list(set(ip_list))

        coros = [
            self._query_single_server(querier, ip, port, s, results)
            for ip, port in ip_list
        ]
        await asyncio.gather(*coros)

        results.sort(key=lambda x: int(x[2]) if str(x[2]).isdigit() else 0, reverse=True)
        return results


server_manager = ServerManager()


async def _send_server_list(reply_func, user_id: int, mid: int, servers_list: list, s: Strings) -> None:
    server_manager.servers_map[(user_id, mid)] = servers_list
    keyboard = await server_manager.build_server_keyboard(user_id, mid, 0)
    await reply_func(s("select_server").format(count=len(servers_list)), reply_markup=keyboard,)


@Client.on_message(filters.command("xash3d", PREFIXES))
@use_chat_lang
async def xash_chat(c: Client, m: Message, s: Strings):
    parts = m.text.split(maxsplit=1)
    if len(parts) == 1:
        await m.reply_text(s("xash3d_example"))
        return

    gamedir = parts[1].strip()
    servers_list = await server_manager.get_servers_info("xash3d", gamedir, s)

    if not servers_list:
        await m.reply_text(s("xash3d_no_servers"))
        return

    mid = m.id
    await _send_server_list(m.reply_text, m.from_user.id, mid, servers_list, s)


@Client.on_message(filters.command("goldsrc", PREFIXES))
@use_chat_lang
async def goldsrc_chat(c: Client, m: Message, s: Strings):
    parts = m.text.split(maxsplit=1)
    if len(parts) == 1:
        await m.reply_text(s("goldsrc_example"))
        return

    gamedir = parts[1].strip()
    servers_list = await server_manager.get_servers_info("goldsrc", gamedir, s)

    if not servers_list:
        await m.reply_text(s("xash3d_no_servers"))
        return

    mid = m.id
    await _send_server_list(m.reply_text, m.from_user.id, mid, servers_list, s)

  
@Client.on_inline_query(filters.regex(r"^xash3d .+", re.IGNORECASE))
@use_chat_lang
async def xash_inline(c: Client, m: InlineQuery, s: Strings):
    parts = m.query.split(maxsplit=1)
    if len(parts) == 1:
        await m.answer(
            [
                InlineQueryResultArticle(
                    title=s("xash3d_example"),
                    input_message_content=InputTextMessageContent(
                        message_text=s("xash3d_example")
                    ),
                )
            ],
            cache_time=0,
        )
        return

    gamedir = parts[1].strip()
    servers_list = await server_manager.get_servers_info("xash3d", gamedir, s)

    results = []
    servers_list.sort(key=lambda x: int(x[2]) if str(x[2]).isdigit() else 0, reverse=True)
    for hostname, map_name, players, maxplayers, info in servers_list[:MAX_INLINE_RESULTS]:
        results.append(
            InlineQueryResultArticle(
                title=hostname,
                input_message_content=InputTextMessageContent(message_text=info),
                description=f"{map_name} ({players}/{maxplayers})",
            )
        )

    await m.answer(results or [
        InlineQueryResultArticle(
            title=s("xash3d_no_servers"),
            input_message_content=InputTextMessageContent(
                message_text=s("xash3d_no_servers")
            ),
        )
    ], cache_time=0)


@Client.on_inline_query(filters.regex(r"^goldsrc .+", re.IGNORECASE))
@use_chat_lang
async def goldsrc_inline(c: Client, m: InlineQuery, s: Strings):
    parts = m.query.split(maxsplit=1)
    if len(parts) == 1:
        await m.answer(
            [
                InlineQueryResultArticle(
                    title=s("goldsrc_example"),
                    input_message_content=InputTextMessageContent(
                        message_text=s("goldsrc_example")
                    ),
                )
            ],
            cache_time=0,
        )
        return

    gamedir = parts[1].strip()
    servers_list = await server_manager.get_servers_info("goldsrc", gamedir, s)

    results = []
    servers_list.sort(key=lambda x: int(x[2]) if str(x[2]).isdigit() else 0, reverse=True)
    for hostname, map_name, players, maxplayers, info in servers_list[:MAX_INLINE_RESULTS]:
        results.append(
            InlineQueryResultArticle(
                title=hostname,
                input_message_content=InputTextMessageContent(message_text=info),
                description=f"{map_name} ({players}/{maxplayers})",
            )
        )

    await m.answer(results or [
        InlineQueryResultArticle(
            title=s("goldsrc_no_servers"),
            input_message_content=InputTextMessageContent(
                message_text=s("goldsrc_no_servers")
            ),
        )
    ], cache_time=0)


@Client.on_callback_query(filters.regex(r"^page_"))
async def handle_pagination(c: Client, query: CallbackQuery):
    parts = query.data.split("_")
    user_id, mid, page = int(parts[1]), int(parts[2]), int(parts[3])

    keyboard = await server_manager.build_server_keyboard(user_id, mid, page)
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=keyboard)


@Client.on_callback_query(filters.regex(r"^server_info_"))
async def handle_server_info(c: Client, query: CallbackQuery):
    parts = query.data.split("_")
    user_id, mid, index = int(parts[2]), int(parts[3]), int(parts[4])

    servers_list = server_manager.servers_map.get((user_id, mid), [])
    if index < len(servers_list):
        server_info = servers_list[index][-1]
        await query.answer()
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

        keys_to_delete = [
            key for key in server_manager.servers_map if key[1] == mid
        ]
        for key in keys_to_delete:
            del server_manager.servers_map[key]

    except Exception as e:
        logger.error(e)


commands.add_command("xash3d", "info")
commands.add_command("goldsrc", "info")
inline_commands.add_command("xash3d <game folder>")
inline_commands.add_command("goldsrc <game folder>")