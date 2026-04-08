# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Elinsrc

import asyncio
import struct
from typing import Optional
import asyncio_dgram
import aiohttp
import re

TIMEOUT = 2.0

GOLDSRC_GAMES = {
    "cstrike": 10,
    "valve": 70,
}

XASH_MS = [
    ("mentality.rip", 27010),
    ("mentality.rip", 27011),
    ("ms2.mentality.rip", 27010),
]

def fmt_time(seconds):
    seconds = int(float(seconds))
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    time_components = []
    if days > 0:
        time_components.append(f"{days}d")
    if hours > 0:
        time_components.append(f"{hours}h")
    if minutes > 0:
        time_components.append(f"{minutes}m")
    if remaining_seconds > 0 or not time_components:
        time_components.append(f"{remaining_seconds}s")

    return ' '.join(time_components)

def remove_color_tags(text):
    if text is None:
        return "None"

    return re.sub(r'\^\d', '', text)

class BaseServerQuery:
    def __init__(self, timeout: float = TIMEOUT):
        self.timeout = timeout

    @staticmethod
    async def _udp_send_recv(ip: str, port: int, data: bytes, timeout: float) -> Optional[bytes]:
        try:
            stream = await asyncio_dgram.connect((ip, port))
            try:
                await stream.send(data)
                recv, _ = await asyncio.wait_for(stream.recv(), timeout=timeout)
                return recv
            except (asyncio.TimeoutError, Exception):
                return None
            finally:
                stream.close()
        except Exception:
            return None


class XashServerQuery(BaseServerQuery):
    def __init__(self, timeout: float = TIMEOUT, xash_ms: list = None):
        super().__init__(timeout)
        self.xash_ms = xash_ms or XASH_MS

    async def get_server_list(self, gamedir: str) -> list:
        servers = []
        query = b"1\xff0.0.0.0:0\x00\\nat\\0\\gamedir\\%b\\clver\\0.21\\buildnum\\0000\x00" % gamedir.encode()

        for host, port in self.xash_ms:
            data = await self._udp_send_recv(host, port, query, 3.0)
            if not data:
                continue

            data = data[6:]
            for i in range(0, len(data), 6):
                ip1, ip2, ip3, ip4, srv_port = struct.unpack(
                    ">BBBBH", data[i : i + 6]
                )
                ip = f"{ip1}.{ip2}.{ip3}.{ip4}"
                if ip == "0.0.0.0":
                    continue
                servers.append((ip, srv_port))

        return servers

    async def query(self, ip: str, port: int) -> Optional[dict]:
        data = await self._udp_send_recv(ip, port, b"\xff\xff\xff\xffinfo 49", self.timeout)

        if not data:
            return {}

        parts = data.decode("utf-8", errors="replace").split("\\")
        info = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}

        return {
            "engine": "xash3d",
            "addr": ip,
            "port": port,
            "host": remove_color_tags(info.get("host")),
            "map": info.get("map"),
            "numcl": info.get("numcl"),
            "maxcl": info.get("maxcl"),
            "gamedir": info.get("gamedir")
        }

    async def get_players(self, ip: str, port: int) -> dict:
        data = await self._udp_send_recv(
            ip, port, b"\xff\xff\xff\xffnetinfo 49 0 3", self.timeout
        )

        if not data:
            return {}

        data = data[16:].decode(errors="replace")
        data = "\\" + data.replace("'", " ").replace("\n", "")
        parts = data.split("\\")[1:]

        if parts and parts[-1] == "":
            parts = parts[:-1]

        if "players" not in parts:
            return {}

        players = {}
        num_players = int(parts[parts.index("players") + 1])
        for i in range(num_players):
            name = parts[parts.index(f"p{i}name") + 1]
            frags = parts[parts.index(f"p{i}frags") + 1]
            time = parts[parts.index(f"p{i}time") + 1]
            players[i] = [remove_color_tags(name), frags, fmt_time(time)]

        return players


class GoldSrcServerQuery(BaseServerQuery):
    def __init__(
        self,
        steam_api_key: str,
        timeout: float = TIMEOUT,
        goldsrc_games: dict = None,
    ):
        super().__init__(timeout)
        self.steam_api_key = steam_api_key
        self.goldsrc_games = goldsrc_games or GOLDSRC_GAMES

    async def get_server_list(self, gamedir: str) -> list:
        appid = self.goldsrc_games.get(gamedir)
        if appid is None:
            return []

        url = "https://api.steampowered.com/IGameServersService/GetServerList/v1/"
        params = {
            "key": self.steam_api_key,
            "filter": f"\\appid\\{appid}",
            "limit": 5000,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                j = await r.json()

        servers = []
        for s in j.get("response", {}).get("servers", []):
            addr = s.get("addr", "")
            if ":" not in addr:
                continue

            if s.get("players", 0) > 32:
                continue

            ip, port = addr.rsplit(":", 1)
            servers.append((ip, port))

        return servers

    async def query(self, ip: str, port: int) -> Optional[dict]:
        data = await self._udp_send_recv(ip, port, b"\xff\xff\xff\xffTSource Engine Query\x00", self.timeout)

        if not data:
            return {}

        if data[:4] != b"\xff\xff\xff\xff":
            return {}

        ptype = data[4]

        if ptype not in (0x49, 0x6D):
            return {}

        off = 5

        def read_str(d: bytes, o: int):
            try:
                end = d.index(b"\x00", o)
                return d[o:end].decode("utf-8", "replace"), end + 1
            except ValueError:
                return "", len(d)

        try:
            if ptype == 0x49:
                off += 1
                name, off = read_str(data, off)
                map_name, off = read_str(data, off)
                gamedir, off = read_str(data, off)
                _, off = read_str(data, off)
                off += 2
                if off + 3 > len(data):
                    return None
                players = data[off]
                max_pl = data[off + 1]
                off += 2
                off += 1
                off += 1
                off += 1
                if off > len(data):
                    return None
                password = bool(data[off])

            else:
                _, off = read_str(data, off)
                name, off = read_str(data, off)
                map_name, off = read_str(data, off)
                gamedir, off = read_str(data, off)
                _, off = read_str(data, off)
                if off + 2 > len(data):
                    return None
                players = data[off]
                max_pl = data[off + 1]
                password = False

            if max_pl == 0 or max_pl > 32:
                return None

            if not name or name.strip() == "":
                return None

        except (IndexError, ValueError):
            return None

        return {
            "engine": "goldsrc",
            "addr": ip,
            "port": port,
            "host": remove_color_tags(name),
            "map": map_name,
            "numcl": players,
            "maxcl": max_pl,
            "gamedir": gamedir,
        }

    async def get_players(self, ip: str, port: int) -> dict:
        req = b"\xff\xff\xff\xffU\xff\xff\xff\xff"
        data = await self._udp_send_recv(ip, port, req, self.timeout)

        if not data or len(data) < 5:
            return {}

        if data[4] == 0x41:
            challenge = data[5:9]
            req = b"\xff\xff\xff\xffU" + challenge
            data = await self._udp_send_recv(ip, port, req, self.timeout)
            if not data or len(data) < 5:
                return {}

        if data[4] != 0x44:
            return {}

        off = 5
        num_players = data[off]
        off += 1

        players = {}
        for _ in range(num_players):
            id = data[off]
            off += 1

            end = data.index(b"\x00", off)
            name = data[off:end].decode("utf-8", errors="replace")
            off = end + 1

            frags = struct.unpack("<i", data[off : off + 4])[0]
            off += 4
            time = struct.unpack("<f", data[off : off + 4])[0]
            off += 4

            players[id] = [remove_color_tags(name), frags, fmt_time(time)]

        return players