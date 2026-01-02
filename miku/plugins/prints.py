# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Elinsrc

import os
import uuid

from hydrogram import Client, filters
from hydrogram.enums import MessageEntityType
from hydrogram.types import Message
from playwright.async_api import async_playwright

from config import PREFIXES
from miku.utils import commands
from miku.utils.localization import Strings, use_chat_lang


@Client.on_message(filters.command("print", PREFIXES))
@use_chat_lang
async def prints(c: Client, m: Message, s: Strings):
    target_url = None

    entities = m.entities or m.caption_entities or []
    for entity in entities:
        if entity.type == MessageEntityType.URL:
            text = m.text or m.caption
            target_url = text[entity.offset : entity.offset + entity.length]
            break
        if entity.type == MessageEntityType.TEXT_LINK:
            target_url = entity.url
            break

    if not target_url and m.reply_to_message:
        entities = m.reply_to_message.entities or m.reply_to_message.caption_entities or []
        for entity in entities:
            if entity.type == MessageEntityType.URL:
                text = m.reply_to_message.text or m.reply_to_message.caption
                target_url = text[entity.offset : entity.offset + entity.length]
                break
            if entity.type == MessageEntityType.TEXT_LINK:
                target_url = entity.url
                break

    if not target_url:
        await m.reply_text(s("print_usage"))
        return

    sent = await m.reply_text(s("print_taking_screenshot"))

    try:
        screenshot_path = await screenshot_page(target_url)
    except Exception as e:
        print(e)
        return

    if not screenshot_path:
        await sent.edit_text(s("print_failed"))
        return

    try:
        await m.reply_photo(photo=screenshot_path)
    except Exception as e:
        await sent.edit_text(s("print_send_failed").format(error=str(e)))
    else:
        await sent.delete()
    finally:
        try:
            os.remove(screenshot_path)
        except OSError:
            pass


async def screenshot_page(target_url: str) -> str:
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    file_path = f"assets/{uuid.uuid4()}.png"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )

        try:
            await page.goto(target_url, wait_until="networkidle", timeout=30_000)
            await page.screenshot(path=file_path, full_page=True)
        finally:
            await browser.close()

    return file_path


commands.add_command("print", "tools")
