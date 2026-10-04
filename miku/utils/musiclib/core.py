# Copyright (c) 2026 goldpulpy
# Original project: https://github.com/goldpulpy/TelegramMusicBot
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.


from __future__ import annotations

from loguru import logger
from typing import TYPE_CHECKING, NoReturn, Self
from urllib.parse import quote

import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup, Tag
from tenacity import retry, stop_after_attempt, wait_exponential

from .data import ServiceConfig, Track
from .exceptions import MusicServiceError

if TYPE_CHECKING:
    from types import TracebackType

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not=A?Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

class Music:
    """Service for searching and downloading music."""

    BASE_URL = "dydki.net"
    SEARCH_ENDPOINT = f"https://{BASE_URL}/"

    def __init__(self, config: ServiceConfig | None = None) -> None:
        """Initialize music service with optional configuration."""
        self._config = config or ServiceConfig()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Self:
        """Context manager entry point."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit point."""
        await self.disconnect()

    async def connect(self) -> None:
        """Initialize HTTP session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=HEADERS)

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def search(self, keyword: str) -> list[Track]:
        """Search for music by keyword."""
        if not self._session:
            msg = "Failed to initialize session"
            raise MusicServiceError(msg)

        url = self.build_search_query(keyword)
        logger.info("Searching music with keyword: {}", keyword)

        return await self._parse_tracks(url)

    async def get_top_hits(self) -> list[Track]:
        """Get top tracks."""
        return await self._parse_tracks(self.SEARCH_ENDPOINT)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
    )
    async def _parse_tracks(self, url: str) -> list[Track]:
        """Parse tracks from the given URL."""
        try:
            if not self._session:
                msg = "Failed to initialize session"
                raise MusicServiceError(msg)

            async with self._session.get(
                url,
                timeout=ClientTimeout(total=self._config.timeout),
                allow_redirects=True,
            ) as response:
                response.raise_for_status()
                soup = BeautifulSoup(await response.text(), "html.parser")
                results = soup.find("div", class_="results")

                if not isinstance(results, Tag):
                    self._raise_results_not_found_error()

                tracks = [
                    Track.from_element(track_data, index)
                    for index, track_data in enumerate(
                        results.find_all("div", class_="chkd"),
                    )
                ]

            logger.info("Found {} tracks", len(tracks))

        except (
            aiohttp.ClientError,
            TimeoutError,
            TypeError,
            ValueError,
        ) as e:
            msg = f"Failed to search music: {e!s}"
            raise MusicServiceError(msg) from e

        return tracks

    def _raise_results_not_found_error(self) -> NoReturn:
        """Raise an error when the results element is missing."""
        msg = "Could not find results element"
        raise TypeError(msg)

    def _raise_file_too_large_error(self, content_length: int) -> None:
        """Raise an error for files that are too large."""
        msg = f"File too large: {content_length} bytes"
        raise MusicServiceError(msg)

    async def _download_data(
        self,
        url: str,
        resource_type: str,
        track_name: str,
    ) -> bytes:
        """Download data."""
        max_size = 50 * 1024 * 1024  # 50MB

        if not self._session:
            msg = "Failed to initialize session"
            raise MusicServiceError(msg)

        logger.info("Downloading {} for track: {}", resource_type, track_name)

        try:
            async with self._session.get(
                url,
                timeout=ClientTimeout(total=self._config.timeout),
            ) as response:
                response.raise_for_status()
                content_length = response.content_length

                if content_length and content_length > max_size:
                    self._raise_file_too_large_error(content_length)

                return await response.read()

        except (aiohttp.ClientError, TimeoutError) as e:
            msg = f"Failed to download {resource_type}"
            raise MusicServiceError(msg) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
    )
    async def get_audio_bytes(self, track: Track) -> bytes:
        """Download music file."""
        return await self._download_data(track.audio_url, "audio", track.name)

    def build_search_query(self, keyword: str) -> str:
        """Build search URL with the keyword as an encoded query value."""
        return f"{self.SEARCH_ENDPOINT}?mp3={quote(keyword)}"
