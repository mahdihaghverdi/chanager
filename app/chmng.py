import asyncio
import json
import socket
import uuid
from asyncio import AbstractEventLoop

from loguru import logger

from core.config import settings

clients: dict[uuid.UUID, "Client"] = {}


class Client:
    def __init__(self, id_, ip, cls_port, connection=None, name=None):
        self.id_ = id_
        self.ip = ip
        self.cls_port = cls_port
        self.connection = connection
        self.name = name
        self.chc: socket.socket | None = None

    def __repr__(self):
        base = f"Client<id: {self.id_}, (ip={self.ip!r}, cls_port: {self.cls_port})"
        if self.name is not None:
            base += f", name={self.name!r}>"
        if self.connection is not None:
            base += f", connection={self.connection}"
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
                await loop.sock_sendall(self.chc, "HealthCheck".encode())
            except ConnectionRefusedError as e:
                while True:
                    try:
                        await self.connect(loop)
                    except ConnectionRefusedError as e:
                        logger.warning(f"{(self.ip, self.cls_port)} is down")
                        logger.debug(
                            f"Trying to reconnect to {(self.ip, self.cls_port)}..."
                        )
                        await asyncio.sleep(
                            settings.CHANAGER_CLIENT_HEALTH_CHECK_INTERVAL
                        )
                    else:
                        break


async def register(connection: socket, loop, address):
    client_raw_data = (await loop.sock_recv(connection, 1024)).decode().strip()
    client_data = json.loads(client_raw_data)

    client_uuid = uuid.uuid4()
    clients[client_uuid] = (
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


async def listen_for_connection(server_socket, loop):
    logger.debug("Chanager is listening for registrations...")
    while True:
        connection, address = await loop.sock_accept(server_socket)
        connection.setblocking(False)
        logger.info(f"Manager got a registration from {address}")
        loop.create_task(register(connection, loop, address))


async def main():
    logger.info(f"Chanager Server [{(settings.CHANAGER_IP, settings.RLS_PORT)}]")
    register_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    register_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    register_listener.setblocking(False)
    register_listener.bind((settings.CHANAGER_IP, settings.RLS_PORT))
    register_listener.listen()

    await listen_for_connection(register_listener, asyncio.get_event_loop())


asyncio.run(main())
