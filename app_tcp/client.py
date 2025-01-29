import asyncio
import json
import random
import socket
import subprocess
import sys

import psutil
from loguru import logger

from core.commands import Commands
from core.config import LogLevels, settings

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

chanager = None
self_id = None


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
        data = data.decode().strip()
        logger.debug(f"Chanager: {data}")

        match data:
            case Commands.health_check:
                await asyncio.sleep(0.001)

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


class EchoClientProtocol:
    def __init__(self, message, on_con_lost):
        self.message = message
        self.on_con_lost = on_con_lost
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        message = {'id': self_id, 'alert': self.message}
        self.transport.sendto(json.dumps(message).encode())

    def datagram_received(self, data, addr):  # noqa
        logger.info('Received:', data.decode().strip(), 'from:', addr)

    def error_received(self, exc):  # noqa
        logger.exception('Error received:', exc)

    def connection_lost(self, _exc):
        self.on_con_lost.set_result(True)


async def send_alert(loop):
    topics = ['CPU Usage is high!', 'Memory is almost full!', 'Malicious activity detected!',
              'System calls are getting slow', 'SWAP partition is full']

    while True:
        on_con_lost = loop.create_future()
        message = random.choice(topics)

        logger.warning(f'Sending {message!r} alert')
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: EchoClientProtocol(message, on_con_lost),  # noqa
            remote_addr=(settings.CHANAGER_IP, settings.ALS_PORT)
        )
        transport.close()
        await asyncio.sleep(settings.CLIENT_ALERT_INTERVAL)


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
    async with asyncio.TaskGroup() as task_group:
        task_group.create_task(command_manager(connection, loop))
        task_group.create_task(send_alert(loop))


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
finally:
    logger.info("Shutting down client...")
