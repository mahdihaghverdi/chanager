import asyncio
import json
import socket
import uuid
from asyncio import AbstractEventLoop

from loguru import logger

from core.config import settings

clients: dict[uuid.UUID, "Client"] = {}


class Client:
    def __init__(self, id_, connection, cls_port, name=None):
        self.id_ = id_
        self.connection = connection
        self.cls_port = cls_port
        self.name = name

    def __repr__(self):
        base = f"Client<id: {self.id_}, connection: {self.connection}"
        if self.name is not None:
            base += f", name={self.name}>"
        else:
            base += ">"
        return base


async def register(connection: socket, loop: AbstractEventLoop):
    client_raw_data = (await loop.sock_recv(connection, 1024)).decode().strip()
    client_data = json.loads(client_raw_data)

    client_uuid = uuid.uuid4()
    clients[client_uuid] = Client(
        client_uuid,
        connection,
        cls_port=client_data["cls_port"],
        name=client_data.get("name"),
    )

    await loop.sock_sendall(
        connection,
        json.dumps({"id": str(client_uuid), "als_port": settings.ALS_PORT}).encode(),
    )
    connection.shutdown(socket.SHUT_RDWR)
    logger.debug(f"Registration for a client with id: {client_uuid!s} is done.")


async def listen_for_connection(server_socket, loop):
    while True:
        connection, address = await loop.sock_accept(server_socket)
        connection.setblocking(False)
        logger.info(f"Manager got a registration from {address}")
        loop.create_task(register(connection, loop))


async def main():
    register_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    register_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    register_listener.setblocking(False)
    register_listener.bind((settings.CHANAGER_IP, settings.RLS_PORT))
    register_listener.listen()

    await listen_for_connection(register_listener, asyncio.get_event_loop())


asyncio.run(main())
