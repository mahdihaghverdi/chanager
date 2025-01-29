import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, FastAPI
from loguru import logger

from core.config import settings
from core.http import get_http_session
from schemas.chmng import ClientListOut, RegisterIn, RegisterOut


class Client:
    def __init__(self, id_: uuid.UUID, ip: str, port: int, name: str | None = None):
        self.id = id_
        self.ip = ip
        self.port = port
        self.name = name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting CHANAGER app...")

    logger.debug("Creating HTTP Client...")
    http_client = await get_http_session()
    logger.info("CHANAGER start complete.")
    yield
    logger.info("Starting CHANAGER app...")

    logger.debug("Closing HTTP Client...")
    await http_client.close()
    logger.info("CHANAGER shutdown complete.")


app = FastAPI(
    debug=settings.DEBUG,
    title=settings.CHANAGER_TITLE,
    version=settings.CHANAGER_VERSION,
    lifespan=lifespan,
)

router = APIRouter()

clients = {}


@router.post("/register", response_model=RegisterOut)
async def register(reg_data: RegisterIn):
    client_uuid = uuid.uuid4()
    clients[str(client_uuid)] = Client(
        id_=client_uuid, ip=reg_data.ip, port=reg_data.port, name=reg_data.name
    )

    return {"id": client_uuid}


async def check_liveness(id_: uuid.UUID, http_client: ClientSession):
    client = clients[id_]
    ip, port = client.ip, client.port

    async with http_client.post(f"http://{ip}:{port}/api/v1/liveness") as resp:
        if resp.status != 200:
            del clients[id_]


@router.get("/list", response_model=ClientListOut)
async def list_clients(
    http_client: Annotated[ClientSession, Depends(get_http_session)],
):
    async with asyncio.TaskGroup() as task_group:
        for client in clients:
            task_group.create_task(check_liveness(client, http_client))

    return {"clients": list(clients.values())}


app.include_router(router, prefix=settings.PREFIX)
