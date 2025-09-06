import re
import struct
import asyncio
import asyncio_dgram
import traceback
from pydantic import BaseModel
from typing import Union

class Address(BaseModel):
    addr: str
    port: int
    def __str__(self) -> str:
        return f"{self.addr}:{self.port}"

ms_list = [
    Address(**{"addr": "mentality.rip", "port": 27010}),
    Address(**{"addr": "mentality.rip", "port": 27011}),
    Address(**{"addr": "ms2.mentality.rip", "port": 27010})
    ]

def remove_color_tags(text):
    if text is None:
        return "None"

    return re.sub(r'\^\d', '', text)

async def send_packet(ip, port, msg, timeout: float) -> Union[bytes, None]:
    stream = await asyncio_dgram.connect((ip, port))
    await stream.send(msg)
    try:
        data, _ = await asyncio.wait_for(stream.recv(), timeout=timeout)
    except asyncio.TimeoutError:
        data = None
    finally:
        stream.close()

    return data

async def get_servers(gamedir:str, nat:bool, ms:Address, timeout:float) -> list[Address]:
    servers = []
    QUERY = b'1\xff0.0.0.0:0\x00\\nat\\%b\\gamedir\\%b\\clver\\0.21\\buildnum\\0000\x00' % (str(nat).encode(), gamedir.encode())

    data = await send_packet(ms.addr, ms.port, QUERY, timeout)

    if not data:
        return None

    data = data[6:]
    for i in range(0, len(data), 6):
        ip1, ip2, ip3, ip4, port = struct.unpack(b">BBBBH", data[i:i+6])
        servers.append(Address(addr=f"{ip1}.{ip2}.{ip3}.{ip4}", port=port))

    servers.pop()  # Last server is 0.0.0.0
    return servers


def format_time(seconds):
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

async def get_players(target: Address, timeout: float, protocol: int) -> dict:
    message = b'\xff\xff\xff\xff' + b'netinfo %b 0 3' % str(protocol).encode()

    data = await send_packet(target.addr, target.port, message, timeout)

    if not data:
        return {}

    data = data[16:]
    data = data.decode(errors='replace')
    data = "\\" + data.replace("'", ' ').replace('\n', '')
    data = data.split("\\")[1:]

    if data[-1] == '':
        data = data[:-1]

    players_list = {}

    # Check protocol version
    if protocol == 49:
        if 'players' in data:
            num_players = int(data[data.index('players') + 1])

            for i in range(num_players):
                name = data[data.index(f"p{i}name") + 1]
                frags = data[data.index(f"p{i}frags") + 1]
                time = data[data.index(f"p{i}time") + 1]

                players_list[i] = [
                    name,
                    frags,
                    format_time(time)
                    ]
    else:
        for i in range(0, len(data), 4):
            if i + 3 < len(data):
                index = data[i]
                name = data[i + 1]
                frags = data[i + 2]
                time = data[i + 3]

                players_list[index] = [
                    name,
                    frags,
                    format_time(time)
                    ]

    return players_list

async def query_servers(target: Address, serverdict, timeout: float) -> None:
    queries = {
        48: b'\xff\xff\xff\xffinfo 48',
        49: b'\xff\xff\xff\xffinfo 49'
    }

    protocol = None
    raw = None

    for prot, query in queries.items():
        raw = await send_packet(target.addr, target.port, query, timeout)

        if raw is None or (b'wrong version' in raw and prot == 48):
            continue

        protocol = prot
        break

    if raw is None:
        return

    raw_str = raw.decode('utf-8', errors='ignore')
    sections = raw_str.split('\\')
    server_info = {sections[i]: sections[i + 1] for i in range(1, len(sections) - 1, 2)}

    players_list = await get_players(target, timeout, protocol)

    server = {
        "addr": f"{target.addr}",
        "port": target.port,
        "host": server_info.get("host"),
        "map": server_info.get("map"),
        "numcl": server_info.get("numcl"),
        "maxcl": server_info.get("maxcl"),
        "gamedir": server_info.get("gamedir"),
        "dm": server_info.get("dm"),
        "team": server_info.get("team"),
        "coop": server_info.get("coop"),
        "password": server_info.get("password"),
        "protocol_ver": protocol,
        "players_list": players_list
    }

    serverdict["servers"].append(server.copy())
