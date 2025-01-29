import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from loguru import logger

from core.config import settings
from core.http import get_http_session
from schemas.chmng import ClientListOut, RegisterIn, RegisterOut


class Client:
    def __init__(self, id_: uuid.UUID, ip: str, port: int, name: str | None = None):
        self.id_ = id_
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


@router.get('/list', response_model=ClientListOut)
async def list_clients():
    # check liveness
    pass



app.include_router(router, prefix=settings.PREFIX)
