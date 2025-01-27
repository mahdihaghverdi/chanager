import asyncio
import json
import socket
import sys

from loguru import logger

from core.config import LogLevels, settings

chanager = None
self_id = None

if settings.LOGLEVEL == LogLevels.INFO:
    logger.add(
        sys.stdout,
        colorize=True,
        format=(
            "<g>{time:YYYY-MMM-DD HH:mm:ss.SSS}</g> "
            "| <c><b>{level:<10}</b></c> "
            "| <b>{message}</b>"
        ),
        level='INFO'
    )
else:
    logger.add(
        sys.stdout,
        colorize=True,
        format=(
            "<g>{time:YYYY-MMM-DD HH:mm:ss.SSS}</g> "
            "| <c><b>{level:<10}</b></c> "
            "| <y>{file}</y>:<y>{function}</y>:<y>{line}</y> "
            "- <b>{message}</b>"
        ),
        level='DEBUG'
    )


class Chanager:
    def __init__(self, als_port):
        self.als_port = als_port

    def __repr__(self):
        return f"Chanager(als_port={self.als_port})"


async def register(loop):
    logger.info('Sending registry request to Chanager...')
    global chanager, self_id

    # create register
    register_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    register_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    register_sock.setblocking(False)

    # connect
    logger.debug(f'Try connecting to {(settings.CHANAGER_IP, settings.RLS_PORT)}')
    await loop.sock_connect(register_sock, (settings.CHANAGER_IP, settings.RLS_PORT))

    logger.debug('Sending profile data...')
    # send data
    await loop.sock_sendall(
        register_sock,
        json.dumps(
            {"name": settings.CLIENT_NAME, "cls_port": settings.CLIENT_CLS_PORT}
        ).encode(),
    )

    # get data
    logger.debug('Getting needed data...')
    chanager_raw_data = (await loop.sock_recv(register_sock, 1024)).decode().strip()
    chanager_data = json.loads(chanager_raw_data)
    self_id = chanager_data["id"]
    chanager = Chanager(als_port=chanager_data["als_port"])
    logger.debug(f"{chanager=}")
    logger.info('Registration complete.')

    # shutdown
    register_sock.shutdown(socket.SHUT_RDWR)


async def command_manager(connection: socket.socket, loop):
    while data := await loop.sock_recv(connection, 1024):
        logger.info(f"Chanager has sent me important message: {data.decode().strip()}")
        await asyncio.sleep(0.1)


async def main():
    loop = asyncio.get_running_loop()

    cls_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cls_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    cls_sock.setblocking(False)
    cls_sock.bind((settings.CLIENT_IP, settings.CLIENT_CLS_PORT))
    cls_sock.listen()

    if sys.argv[1] == "1":
        await register(loop)

    logger.info(
        f"Client [{(settings.CLIENT_IP, settings.CLIENT_CLS_PORT)}] is listening..."
    )
    connection, address = await loop.sock_accept(cls_sock)
    connection.setblocking(False)

    while address[0] != settings.CHANAGER_IP:
        connection.shutdown(socket.SHUT_RDWR)
        connection, address = await loop.sock_accept(cls_sock)
        connection.setblocking(False)

    # real chanager has established a connection
    await command_manager(connection, loop)


asyncio.run(main())
