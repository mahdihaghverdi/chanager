import asyncio
import json
import socket

from loguru import logger

from core.config import settings

chanager = None
self_id = None


class Chanager:
    def __init__(self, als_port):
        self.als_port = als_port

    def __repr__(self):
        return f"Chanager(als_port={self.als_port})"


async def register():
    global chanager, self_id

    register_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    register_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    register_sock.setblocking(False)
    loop = asyncio.get_running_loop()
    await loop.sock_connect(register_sock, (settings.CHANAGER_IP, settings.RLS_PORT))
    await loop.sock_sendall(
        register_sock,
        json.dumps(
            {"name": settings.CLIENT_NAME, "cls_port": settings.CLIENT_CLS_PORT}
        ).encode(),
    )
    chanager_raw_data = (await loop.sock_recv(register_sock, 1024)).decode().strip()
    chanager_data = json.loads(chanager_raw_data)
    self_id = chanager_data["id"]
    chanager = Chanager(als_port=chanager_data["als_port"])
    logger.debug(f"{chanager=}")
    register_sock.shutdown(socket.SHUT_RDWR)


asyncio.run(register())
