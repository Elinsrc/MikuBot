# Copyright (c) 2025 goldpulpy
# Original project: https://github.com/goldpulpy/TelegramMusicBot
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.


from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

headers_path = Path(__file__).parent / "headers.json"


@dataclass
class ServiceConfig:
    """Configuration for music service."""

    timeout: int = 30
    headers: dict = field(
        default_factory=lambda: json.load(
            Path.open(headers_path, encoding="utf-8"),
        ),
    )


@dataclass
class Track:
    """Track data class."""

    index: int
    name: str
    title: str
    performer: str
    audio_url: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Track:
        """Create Track from a dictionary."""
        return cls(
            index=int(data["index"]),
            name=data["name"],
            title=data["title"],
            performer=data["performer"],
            audio_url=data["audio_url"],
        )

    @classmethod
    def from_element(
        cls,
        element: BeautifulSoup | Tag,
        index: int,
    ) -> Track:
        """Create Track from BeautifulSoup element."""
        artist_name_element = element.find(class_="playlist-name-artist")
        track_name_element = element.find(class_="playlist-name-title")
        if artist_name_element is None or track_name_element is None:
            msg = "Could not find artist name element"
            raise ValueError(msg)

        performer = artist_name_element.text.strip()
        title = track_name_element.text.strip()

        full_name = f"{performer} - {title}"

        audio_url = element.find(class_="playlist-play")
        if not isinstance(audio_url, Tag):
            msg = "Could not find audio URL element"
            raise TypeError(msg)
        audio_url = audio_url.get("data-url", "")

        return cls(
            index=index,
            name=full_name,
            title=title,
            performer=performer,
            audio_url=str(audio_url),
        )
