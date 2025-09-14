# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Elinsrc

import io
from mutagen import File

from hydrogram import Client, filters
from hydrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import PREFIXES
from miku.utils import commands
from miku.utils.musiclib import Music
from miku.utils.localization import Strings, use_chat_lang


class MusicService:
    def __init__(self):
        self.tracks = []

    def get_tracks(self):
        return self.tracks

    def set_tracks(self, tracks):
        self.tracks = tracks

    async def build_track_buttons(self, tracks, page_number, mid):
        count = len(tracks)
        page_size = 10
        page_count = (count + page_size - 1) // page_size

        buttons = []
        for index in range((page_number - 1) * page_size, min(page_number * page_size, count)):
            track = tracks[index]
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"{track.performer} - {track.title}",
                        callback_data=f"send_music|{index}|{mid}",
                    )
                ]
            )

        navigation_buttons = []
        if page_number > 1:
            navigation_buttons.append(
                InlineKeyboardButton(
                    "⬅️", callback_data=f"prev_music_page|{page_number - 1}|{mid}"
                )
            )
        else:
            navigation_buttons.append(InlineKeyboardButton("⏺️", callback_data="ignore"))

        navigation_buttons.append(
            InlineKeyboardButton(f"{page_number}/{page_count}", callback_data="ignore")
        )

        if page_number < page_count:
            navigation_buttons.append(
                InlineKeyboardButton(
                    "➡️", callback_data=f"next_music_page|{page_number + 1}|{mid}"
                )
            )
        else:
            navigation_buttons.append(InlineKeyboardButton("⏺️", callback_data="ignore"))

        buttons.append(navigation_buttons)
        buttons.append(
            [InlineKeyboardButton("⬇️", callback_data=f"send_all_music|{page_size}|{page_number}|{mid}")]
        )
        buttons.append([InlineKeyboardButton("🗑️", callback_data="delete_message")])

        return InlineKeyboardMarkup(buttons)


music_service = MusicService()


@Client.on_message(filters.command("music", PREFIXES))
@use_chat_lang
async def music_cmd(c: Client, m: Message, s: Strings):
    parts = m.text.split(None, 1)
    if len(parts) == 1:
        buttons = [[InlineKeyboardButton(s("top_musics"), callback_data=f"get_hits|{m.id}")]]
        await m.reply_text(s("music_example"), reply_markup=InlineKeyboardMarkup(buttons))
        return

    keyword = parts[1]
    async with Music() as service:
        tracks = await service.search(keyword)
        music_service.set_tracks(tracks)

    tracks = music_service.get_tracks()
    if tracks:
        await m.reply_text(
            s("music_found").format(tracks=len(tracks)),
            reply_markup=await music_service.build_track_buttons(tracks, 1, m.id),
        )
    else:
        await m.reply_text(s("music_not_found"))


@Client.on_callback_query(filters.regex("^get_hits"))
@use_chat_lang
async def send_hits(c: Client, cb: CallbackQuery, s: Strings):
    _, mid = cb.data.split("|")

    await cb.answer()

    async with Music() as service:
        category = s("top_musics")
        tracks = await service.get_top_hits()
        music_service.set_tracks(tracks)

    tracks = music_service.get_tracks()
    if tracks:
        message_text = s("music_category_found").format(tracks=len(tracks), category=category)
        await cb.message.edit_text(
            message_text,
            reply_markup=await music_service.build_track_buttons(tracks, 1, mid),
        )
    else:
        await cb.message.edit_text(s("no_tracks_found"))


@Client.on_callback_query(filters.regex("^send_music"))
async def play_track(c: Client, cb: CallbackQuery):
    _, track_index, mid = cb.data.split("|")
    track_index = int(track_index)

    await cb.answer()
    await cb.message.delete()

    tracks = music_service.get_tracks()
    if track_index < len(tracks):
        async with Music() as service:
            track = tracks[track_index]
            audio_bytes = await service.get_audio_bytes(track)

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = f"{track.title}.mp3"

            audio = File(audio_file)
            duration = audio.info.length

            await cb.message.reply_audio(
                audio_file,
                title=track.title,
                duration=int(duration),
                performer=track.performer,
                reply_to_message_id=int(mid),
            )


@Client.on_callback_query(filters.regex("^send_all_music"))
async def send_all_tracks(c: Client, cb: CallbackQuery):
    _, page_size, page_number, mid = cb.data.split("|")
    tracks = music_service.get_tracks()

    await cb.answer()
    await cb.message.delete()

    start_index = (int(page_number) - 1) * int(page_size)
    end_index = min(start_index + int(page_size), len(tracks))

    for index in range(start_index, end_index):
        track = tracks[index]
        async with Music() as service:
            audio_bytes = await service.get_audio_bytes(track)

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = f"{track.title}.mp3"

            audio = File(audio_file)
            duration = audio.info.length

            await cb.message.reply_audio(
                audio_file,
                title=track.title,
                duration=int(duration),
                performer=track.performer,
                reply_to_message_id=int(mid),
            )


@Client.on_callback_query(filters.regex("(^next_music_page)|(^prev_music_page)"))
async def change_page(c: Client, cb: CallbackQuery):
    _, page_number, mid = cb.data.split("|")
    tracks = music_service.get_tracks()
    await cb.answer()
    await cb.message.edit_reply_markup(
        reply_markup=await music_service.build_track_buttons(tracks, int(page_number), mid)
    )


commands.add_command("music", "tools")
