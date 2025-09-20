# SPDX-License-Identifier: MIT
# Copyright (c) 2018-2025

from __future__ import annotations

import re
from hydrogram import Client, filters
from hydrogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
    Message,
)
from config import PREFIXES
from miku.utils import commands, http, inline_commands
from miku.utils.localization import Strings, use_chat_lang

API_KEY = '02048c30539276ca0aaca33944aa39c1'
url = 'http://api.openweathermap.org/data/2.5/weather'
headers = {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; M2012K11AG Build/SQ1D.211205.017)"}

status_emojis = {
    "01d": "☀️",
    "01n": "🌙",
    "02d": "🌤️",
    "02n": "🌙☁️",
    "03d": "⛅",
    "03n": "☁️",
    "04d": "☁️☁️",
    "04n": "☁️☁️",
    "09d": "🌧️",
    "09n": "🌧️",
    "10d": "🌦️",
    "10n": "🌧️",
    "11d": "⛈️",
    "11n": "⛈️",
    "13d": "❄️",
    "13n": "❄️",
    "50d": "🌫️",
    "50n": "🌫️",
}

@Client.on_message(filters.command("weather", PREFIXES))
@Client.on_inline_query(filters.regex(r"^(weather) .+", re.IGNORECASE))
@use_chat_lang
async def weather(c: Client, m: InlineQuery | Message, s: Strings):
    text = m.text if isinstance(m, Message) else m.query
    if len(text.split(maxsplit=1)) == 1:
        if isinstance(m, Message):
            await m.reply_text(s("weather_usage"))
            return

        await m.answer(
            [
                InlineQueryResultArticle(
                    title=s("no_location"),
                    input_message_content=InputTextMessageContent(
                        message_text=s("weather_no_location"),
                    ),
                )
            ],
            cache_time=0,
        )
        return

    # Запрос к OpenWeatherMap
    r = await http.get(
        url,
        headers=headers,
        params={
            'lang': s("weather_lang"),
            'units': 'metric',
            'APPID': API_KEY,
            'q': text.split(None, 1)[1],
        },
    )

    weather = r.json()

    if str(weather.get("cod")) == "404":
        if isinstance(m, Message):
            await m.reply_text(s("location_not_found"))
            return

        await m.answer(
            [
                InlineQueryResultArticle(
                    title=s("location_not_found"),
                    input_message_content=InputTextMessageContent(
                        message_text=s("location_not_found"),
                    ),
                )
            ],
            cache_time=0,
        )
        return

    icon_code = weather["weather"][0]["icon"]
    emoji = status_emojis.get(icon_code, "❔")
    city = weather["name"]
    country = weather["sys"]["country"]
    temp = weather["main"]["temp"]
    desc = weather["weather"][0]["description"]
    wind = weather["wind"]["speed"]
    humidity = weather["main"]["humidity"]
    pressure = weather["main"]["pressure"] / 1000 * 750.06

    res = (
        f"{emoji} {s('weather_in')} {country}/{city}\n"
        f"🌡 {s('weather_temp')} {temp:.0f}°C\n"
        f"💨 {s('weather_wind')} {wind} m/s\n"
        f"💧 {s('weather_humidity')} {humidity}%\n"
        f"📋 {s('weather_description')} {desc}\n"
        f"🔽 {s('weather_pressure')} {pressure:.0f}"
    )

    if isinstance(m, Message):
        await m.reply_text(res)
        return

    await m.answer(
        [
            InlineQueryResultArticle(
                title=f"{s('weather_click')}",
                input_message_content=InputTextMessageContent(message_text=res),
                description=f"{weather['sys']['country']}/{weather['name']}"
            )
        ],
        cache_time=0,
    )

commands.add_command("weather", "info")
inline_commands.add_command("weather <location>")
