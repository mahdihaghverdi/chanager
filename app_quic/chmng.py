import asyncio
import json
import socket
import sys
import textwrap
import uuid
from asyncio import AbstractEventLoop
from math import floor
import struct
from typing import Dict, Optional
from loguru import logger

# Quic
from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
# from aioquic.quic.logger import QuicFileLogger
from aioquic.tls import SessionTicket


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
                        logger.info(f'Connection to {(self.ip, self.cls_port)} reestablished')
                        self.retries = 1
                        self.secs = 2
                        break


async def admin_commands(connection: socket.socket, loop):
    await loop.sock_sendall(
        connection,
        textwrap.dedent(
            '''\
                        You can choose from these commands:

                        list
                        cpu ID
                        memory ID
                        profile ID
                        processes ID
                        '''
        ).encode()
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
                    logger.debug('`list` was chosen.')
                    await loop.sock_sendall(
                        connection,
                        textwrap.dedent(
                            f'''\
                        List of all registered clients
                        ------------------------------
                        
                        {'\n'.join(f'{ind}: {key}' for ind, key in zip(map(str, range(1, len(clients) + 1)), clients))}
                        '''
                        ).encode()
                    )

                case Commands.cpu:
                    logger.debug('`cpu` was chosen.')
                    client = clients[id_[0]]
                    await loop.sock_sendall(client.chc, Commands.cpu.encode())
                    report = (await loop.sock_recv(client.chc, 1024)).decode().strip()
                    await loop.sock_sendall(connection, f'CPU: {report}\n'.encode())

                case Commands.memory:
                    logger.debug('`memory` was chosen.')
                    client = clients[id_[0]]
                    await loop.sock_sendall(client.chc, Commands.memory.encode())
                    report = (await loop.sock_recv(client.chc, 1024)).decode().strip()
                    await loop.sock_sendall(connection, f'Memory: {report}\n'.encode())

                case Commands.profile:
                    logger.debug('`profile` was chosen.')
                    client = clients[id_[0]]
                    await loop.sock_sendall(connection, f'Profile: {client}\n'.encode())

                case Commands.processes:
                    logger.debug('`processes` was chosen.')
                    client = clients[id_[0]]
                    await loop.sock_sendall(client.chc, Commands.processes.encode())
                    report = (await loop.sock_recv(client.chc, 1024)).decode().strip()
                    await loop.sock_sendall(connection, f'Running Processes: {report}\n'.encode())

        except KeyError:
            await loop.sock_sendall(connection, b'Wrong client key!\n')
        except IndexError:
            await loop.sock_sendall(connection, b'Key not provided!\n')


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
        cid = message['id']
        alert_msg = message['alert']
        logger.critical(f'ALERT: <ID:{cid}> said: <{alert_msg!r}> (Address: {address})')


class RegistrationProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event: QuicEvent):
        if isinstance(event, StreamDataReceived):
            client_data = json.loads(event.data)

            client_uuid = uuid.uuid4()
            clients[str(client_uuid)] = (
                client := Client(
                    id_=client_uuid,
                    ip="localhost",
                    cls_port=client_data["cls_port"],
                    name=client_data.get("name"),
                )
            )

            response = json.dumps({"id": str(client_uuid), "als_port": settings.ALS_PORT}).encode()
            response_length = struct.pack("!H", len(response))
            self._quic.send_stream_data(event.stream_id, response_length + response, end_stream=True)

            self._quic.close(error_code=0)
            self._transport.close()
            logger.debug(f"Registration for {client} is done.")


            print(clients)
            # await asyncio.sleep(settings.CHANAGER_WAIT_TO_CONNECT)
            # logger.debug(f"Trying to connect to: {(client.ip, client.cls_port)}")

            # await client.connect(loop)
            # loop.create_task(client.health_check(loop))


class SessionTicketStore:
    """
    Simple in-memory store for session tickets.
    """

    def __init__(self) -> None:
        self.tickets: Dict[bytes, SessionTicket] = {}

    def add(self, ticket: SessionTicket) -> None:
        self.tickets[ticket.ticket] = ticket

    def pop(self, label: bytes) -> Optional[SessionTicket]:
        return self.tickets.pop(label, None)


async def main(
    configuration: QuicConfiguration,
    session_ticket_store: SessionTicketStore,
) -> None:
    logger.info(
        f"Chanager Server [{(settings.CHANAGER_IP, settings.RLS_PORT)}] `(Admin: {settings.CMD_PORT})`"
    )

    await serve(
        # settings.CHANAGER_IP,
        "localhost",
        settings.RLS_PORT,
        configuration=configuration,
        create_protocol=RegistrationProtocol,
        session_ticket_fetcher=session_ticket_store.pop,
        session_ticket_handler=session_ticket_store.add,
        retry=True
    )
    await asyncio.Future()


if __name__ == '__main__':
    configuration_register = QuicConfiguration(
        alpn_protocols=["ch-register"],
        is_client=False
    )

    configuration_register.load_cert_chain("app_quic/certs/ssl_cert.pem", "app_quic/certs/ssl_key.pem")

    try:        
        asyncio.run(
            main(
                configuration=configuration_register,
                session_ticket_store=SessionTicketStore()
            )
        )
    except KeyboardInterrupt:
        pass
    finally:
        logger.info('Shutting down the server...')
