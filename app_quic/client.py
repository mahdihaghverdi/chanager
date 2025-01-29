import asyncio
import json
import random
import socket
import subprocess
import sys
import struct
from typing import Optional, cast

import psutil
from loguru import logger

# Quic
from aioquic.asyncio.client import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
# from aioquic.quic.logger import QuicFileLogger

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


def save_session_ticket(ticket):
    """
    Callback which is invoked by the TLS engine when a new session ticket
    is received.
    """
    logger.info("New session ticket received")
    if False:
        with open(args.session_ticket, "wb") as fp:
            pickle.dump(ticket, fp)


class RegisterClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ack_waiter: Optional[asyncio.Future[str]] = None

    
    async def register(self):
        logger.info('Sending registry request to Chanager...')

        data = json.dumps(
            {"name": settings.CLIENT_NAME, "cls_port": settings.CLIENT_CLS_PORT}
        ).encode()

        # send query and wait for answer
        stream_id = self._quic.get_next_available_stream_id()
        self._quic.send_stream_data(stream_id, data, end_stream=True)
        waiter = self._loop.create_future()
        self._ack_waiter = waiter
        self.transmit()

        return await asyncio.shield(waiter)


    def quic_event_received(self, event: QuicEvent) -> None:
        if self._ack_waiter is not None:
            if isinstance(event, StreamDataReceived):
                # parse answer
                # length = struct.unpack("!H", bytes(event.data[:2]))[0]
                print(event.data)

                # parse answer
                length = struct.unpack("!H", bytes(event.data[:2]))[0]
                answer = event.data[2 : 2 + length]

                # return answer
                waiter = self._ack_waiter
                self._ack_waiter = None
                waiter.set_result(answer)


async def main(configuration: QuicConfiguration) -> None:
    logger.debug(f"Connecting to {settings.CHANAGER_IP}:{settings.RLS_PORT}")
    if sys.argv[1] == "1":
        async with connect(
            # settings.CHANAGER_IP,
            "localhost",
            settings.RLS_PORT,
            configuration=configuration,
            session_ticket_handler=save_session_ticket,
            create_protocol=RegisterClientProtocol,
        ) as client:
            client = cast(RegisterClientProtocol, client)
            answer = await client.register()
            logger.info("Received DNS answer\n%s" % answer)

            global self_id, chanager
            chanager_data = json.loads(answer)
            self_id = chanager_data["id"]
            chanager = Chanager(als_port=chanager_data["als_port"])
            logger.debug(f"{chanager=}")
            logger.info('Registration complete.')


if __name__ == '__main__':
    configuration_register = QuicConfiguration(
        alpn_protocols=["ch-register"],
        is_client=True
    )

    configuration_register.load_verify_locations("app_quic/certs/pycacert.pem")
    # configuration_register.verify_mode = ssl.CERT_NONE

    try:        
        asyncio.run(
            main(configuration=configuration_register)
        )
    except KeyboardInterrupt:
        pass
    finally:
        logger.info('Shutting down the server...')