# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Elinsrc

from __future__ import annotations

from .core import database

conn = database.get_conn()


async def get_antispam(chat_id: int) -> bool:
    cursor = await conn.execute(
        "SELECT antispam_enabled FROM spam_users WHERE chat_id = ?", (chat_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return False
    return bool(row[0])


async def enable_antispam(chat_id: int, mode: bool):
    result = await conn.execute(
        "UPDATE spam_users SET antispam_enabled = ? WHERE chat_id = ?", (int(mode), chat_id)
    )
    if result.rowcount == 0:
        await conn.execute(
            "INSERT INTO spam_users (chat_id, antispam_enabled) VALUES (?, ?)", (chat_id, int(mode))
        )
    await conn.commit()

