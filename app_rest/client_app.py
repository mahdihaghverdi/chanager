from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from loguru import logger

from core.config import settings
from core.http import get_http_session
from schemas.chmng import RegisterIn

self_id = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global self_id

    logger.info("Starting Client app...")

    logger.debug("Creating HTTP Client...")
    http_client = await get_http_session()

    logger.debug('Registering...')
    async with http_client.post(
        f'http://{settings.CHANAGER_IP}:{settings.CHANAGER_PORT}'
        f'/api/{settings.API_VERSION}/register',
        json=RegisterIn(
            ip=settings.CLIENT_IP,
            port=settings.CLIENT_PORT,
            name=settings.CLIENT_TITLE
        ).model_dump(mode='json')
    ) as resp:
        if resp.status == 200:
            json = await resp.json()
            self_id = json['id']

    logger.info("Client start complete.")
    yield
    logger.info("Starting Client app...")

    logger.debug("Closing HTTP Client...")
    await http_client.close()
    logger.info("Client shutdown complete.")


app = FastAPI(
    debug=settings.DEBUG,
    title=settings.CLIENT_TITLE,
    version=settings.CLIENT_VERSION,
    lifespan=lifespan,
)

router = APIRouter()

app.include_router(router, prefix=settings.PREFIX, tags=["register"])
