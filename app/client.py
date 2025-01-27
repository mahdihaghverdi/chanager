import asyncio
import json
import socket
import subprocess
import sys

import psutil
from loguru import logger

from core.commands import Commands
from core.config import LogLevels, settings

chanager = None
self_id = None

logger.remove()
if settings.LOGLEVEL == LogLevels.INFO:
    logger.add(
        sys.stdout,
        colorize=True,
        format=(
            "<g>{time:YYYY-MMM-DD HH:mm:ss.SSS}</g> "
            "| <c><b>{level:<10}</b></c> "
            "| <bold>{message}</bold>"
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
            "- <bold>{message}</bold>"
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
        await asyncio.sleep(0.001)
        data = data.decode().strip()
        logger.debug(f"Chanager has sent me important message: {data}")

        match data:
            case Commands.cpu:
                res = psutil.cpu_percent(percpu=True)
                await loop.sock_sendall(connection, f'{res}'.encode())

            case Commands.memory:
                to_mb = lambda x: f'{x // 1024 // 1024} MB'  # noqa

                res = psutil.virtual_memory()
                to_send = ', '.join(
                    [
                        'Total: ' + to_mb(res.total),
                        'Available: ' + to_mb(res.available),
                        'Usage: ' + str(res.percent) + "%"
                    ]
                )
                await loop.sock_sendall(connection, to_send.encode())

            case Commands.processes:
                res = subprocess.getoutput('ps uaxw | wc -l')
                await loop.sock_sendall(connection, f'{res}'.encode())


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
