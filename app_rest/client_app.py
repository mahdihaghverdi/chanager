from contextlib import asynccontextmanager
from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from loguru import logger
from starlette import status

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
        f'{settings.PREFIX}/register',
        json=RegisterIn(
            ip=settings.CLIENT_IP,
            port=settings.CLIENT_PORT,
            name=settings.CLIENT_TITLE
        ).model_dump(mode='json')
    ) as resp:
        json = await resp.json()
        if resp.status == 200:
            self_id = json['id']
        else:
            raise TypeError(f"Could not register: {json}")

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


@router.post('/register', status_code=status.HTTP_204_NO_CONTENT)
async def register(http_client: Annotated[ClientSession, Depends(get_http_session)]):
    global self_id

    if self_id is None:
        async with http_client.post(
            f'http://{settings.CHANAGER_IP}:{settings.CHANAGER_PORT}'
            f'{settings.PREFIX}/register',
            json=RegisterIn(
                ip=settings.CLIENT_IP,
                port=settings.CLIENT_PORT,
                name=settings.CLIENT_TITLE
            ).model_dump(mode='json')
        ) as resp:
            json = await resp.json()
            if resp.status == 200:
                self_id = json['id']
            else:
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail=f'Could\'nt register: {json}'
                )


app.include_router(router, prefix=settings.PREFIX)
