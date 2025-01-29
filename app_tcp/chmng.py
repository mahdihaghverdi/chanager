import asyncio
import json
import socket
import sys
import textwrap
import uuid
from asyncio import AbstractEventLoop
from math import floor

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
            "| <b>{message}</b>"
        ),
        level="INFO",
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
        level="DEBUG",
    )

clients: dict[str, "Client"] = {}


class Client:
    def __init__(self, id_, ip, cls_port, name=None):
        self.id_ = id_
        self.ip = ip
        self.cls_port = cls_port
        self.name = name
        self.chc: socket.socket | None = None
        self.retries = 1
        self.secs = 2

    def __repr__(self):
        base = f"Client<id: {self.id_}, (ip={self.ip!r}, cls_port: {self.cls_port})"
        if self.name is not None:
            base += f", name={self.name!r}>"
        else:
            base += ">"
        return base

    async def connect(self, loop):
        chc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        chc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        chc.setblocking(False)
        await loop.sock_connect(chc, (self.ip, self.cls_port))
        logger.debug(f"Connection with {(self.ip, self.cls_port)} is established.")
        self.chc = chc

    async def health_check(self, loop: AbstractEventLoop):
        logger.debug(f"HealthCheck for {(self.ip, self.cls_port)} is running...")
        while True:
            await asyncio.sleep(settings.CHANAGER_CLIENT_HEALTH_CHECK_INTERVAL)
            try:
                await loop.sock_sendall(self.chc, Commands.health_check.encode())
            except (ConnectionRefusedError, BrokenPipeError):
                while True:
                    try:
                        await self.connect(loop)
                    except ConnectionRefusedError:
                        logger.warning(f"{(self.ip, self.cls_port)} is down")
                        logger.debug(
                            f"[{self.retries}/100] Trying to reconnect to "
                            f"{(self.ip, self.cls_port)} after {self.secs} seconds"
                        )
                        await asyncio.sleep(self.secs)
                        self.retries += 1
                        self.secs = floor(self.secs * 1.5)
                    else:
                        logger.info(
                            f"Connection to {(self.ip, self.cls_port)} reestablished"
                        )
                        self.retries = 1
                        self.secs = 2
                        break


lock = asyncio.Lock()


async def register(connection: socket.socket, loop, address):
    async with lock:
        client_raw_data = (await loop.sock_recv(connection, 1024)).decode().strip()
        client_data = json.loads(client_raw_data)

        client_uuid = uuid.uuid4()
        clients[str(client_uuid)] = (
            client := Client(
                id_=client_uuid,
                ip=address[0],
                cls_port=client_data["cls_port"],
                name=client_data.get("name"),
            )
        )

        await loop.sock_sendall(
            connection,
            json.dumps({"id": str(client_uuid), "als_port": settings.ALS_PORT}).encode(),
        )
        connection.shutdown(socket.SHUT_RDWR)
        logger.debug(f"Registration for {client} is done.")

        await asyncio.sleep(settings.CHANAGER_WAIT_TO_CONNECT)
        logger.debug(f"Trying to connect to: {(client.ip, client.cls_port)}")

        await client.connect(loop)
        loop.create_task(client.health_check(loop))


async def admin_commands(connection: socket.socket, loop):
    await loop.sock_sendall(
        connection,
        textwrap.dedent(
            """\
            You can choose from these commands:

            list
            cpu ID
            memory ID
            profile ID
            processes ID
            """
        ).encode(),
    )
    while data := await loop.sock_recv(connection, 1024):
        await asyncio.sleep(0.001)
        try:
            command, *id_ = data.decode().strip().split()
        except Exception:  # noqa
            continue

        try:
            match command:
                case Commands.list:
                    logger.debug("`list` was chosen.")
                    await loop.sock_sendall(
                        connection,
                        textwrap.dedent(
                            f"""\
                            List of all registered clients
                            ------------------------------
                            
                            {'\n'.join(f'{ind:>2}: {key}' for ind, key in zip(map(str, range(1, len(clients) + 1)), clients))}
                            """
                        ).encode(),
                    )

                case Commands.cpu:
                    logger.debug("`cpu` was chosen.")
                    client = clients[id_[0]]
                    await loop.sock_sendall(client.chc, Commands.cpu.encode())
                    report = (await loop.sock_recv(client.chc, 1024)).decode().strip()
                    await loop.sock_sendall(connection, f"CPU: {report}\n".encode())

                case Commands.memory:
                    logger.debug("`memory` was chosen.")
                    client = clients[id_[0]]
                    await loop.sock_sendall(client.chc, Commands.memory.encode())
                    report = (await loop.sock_recv(client.chc, 1024)).decode().strip()
                    await loop.sock_sendall(connection, f"Memory: {report}\n".encode())

                case Commands.profile:
                    logger.debug("`profile` was chosen.")
                    client = clients[id_[0]]
                    await loop.sock_sendall(connection, f"Profile: {client}\n".encode())

                case Commands.processes:
                    logger.debug("`processes` was chosen.")
                    client = clients[id_[0]]
                    await loop.sock_sendall(client.chc, Commands.processes.encode())
                    report = (await loop.sock_recv(client.chc, 1024)).decode().strip()
                    await loop.sock_sendall(
                        connection, f"Running Processes: {report}\n".encode()
                    )

        except KeyError:
            await loop.sock_sendall(connection, b"Wrong client key!\n")
        except IndexError:
            await loop.sock_sendall(connection, b"Key not provided!\n")


async def listen_for_registration(server_socket, loop):
    logger.info("Chanager is listening for registrations...")
    while True:
        connection, address = await loop.sock_accept(server_socket)
        connection.setblocking(False)
        logger.info(f"Manager got a registration from {address}")
        loop.create_task(register(connection, loop, address))


async def listen_for_admin(server_socket, loop):
    logger.info("Chanager is listening for admin...")
    while True:
        connection, address = await loop.sock_accept(server_socket)
        connection.setblocking(False)
        logger.info(f"An Admin is connected to me...")
        loop.create_task(admin_commands(connection, loop))


class EchoServerProtocol:
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):  # noqa
        message = json.loads(data.decode().strip())
        cid = message["id"]
        alert_msg = message["alert"]
        logger.critical(f"ALERT: <ID:{cid}> said: <{alert_msg!r}> (Address: {address})")


async def main():
    logger.info(
        f"Chanager Server [{(settings.CHANAGER_IP, settings.RLS_PORT)}] `(Admin: {settings.CMD_PORT})`"
    )
    rls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rls.setblocking(False)
    rls.bind((settings.CHANAGER_IP, settings.RLS_PORT))
    rls.listen()

    cmd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cmd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    cmd.setblocking(False)
    cmd.bind((settings.CHANAGER_IP, settings.CMD_PORT))
    cmd.listen()

    loop = asyncio.get_running_loop()

    logger.info(f"Chanager UDP socket [{settings.ALS_PORT}] is listening...")
    transport, _ = await loop.create_datagram_endpoint(
        EchoServerProtocol,  # noqa
        local_addr=(settings.CHANAGER_IP, settings.ALS_PORT),
    )

    async with asyncio.TaskGroup() as task_group:
        task_group.create_task(listen_for_registration(rls, loop))
        task_group.create_task(listen_for_admin(cmd, loop))


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
finally:
    logger.info("Shutting down the server...")
