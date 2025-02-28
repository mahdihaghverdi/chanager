import asyncio
import subprocess
from contextlib import asynccontextmanager
from typing import Annotated

import psutil
from aiohttp import ClientSession
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from loguru import logger
from starlette import status

from core.config import settings
from core.http import get_http_session
from schemas.chmng import RegisterIn
from schemas.client import CPUOut, MemoryOut

self_id = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global self_id

    logger.info("Starting Client app...")

    logger.debug("Creating HTTP Client...")
    http_client = await get_http_session()

    await asyncio.sleep(2)
    logger.debug("Registering...")
    async with http_client.post(
        f"http://{settings.CHANAGER_IP}:{settings.CHANAGER_PORT}" f"/api/v1/register",
        json=RegisterIn(
            ip=settings.CLIENT_IP, port=settings.CLIENT_PORT, name=settings.CLIENT_TITLE
        ).model_dump(mode="json"),
    ) as resp:
        json = await resp.json()
        if resp.status == 200:
            self_id = json["id"]
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


@router.post("/register", status_code=status.HTTP_204_NO_CONTENT)
async def register(http_client: Annotated[ClientSession, Depends(get_http_session)]):
    global self_id

    if self_id is None:
        async with http_client.post(
            f"http://{settings.CHANAGER_IP}:{settings.CHANAGER_PORT}"
            f"/api/v1/register",
            json=RegisterIn(
                ip=settings.CLIENT_IP,
                port=settings.CLIENT_PORT,
                name=settings.CLIENT_TITLE,
            ).model_dump(mode="json"),
        ) as resp:
            json = await resp.json()
            if resp.status == 200:
                self_id = json["id"]
            else:
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail=f"Couldn't register: {json}",
                )


@router.post("/liveness")
async def liveness():
    return


@router.get('/cpu', response_model=CPUOut)
async def cpu():
    return {'cpu_percents': psutil.cpu_percent(percpu=True)}


@router.get('/memory', response_model=MemoryOut)
async def memory():
    to_mb = lambda x: f"{x // 1024 // 1024} MB"  # noqa

    mem = psutil.virtual_memory()
    return {
        'total': to_mb(mem.total),
        'available': to_mb(mem.available),
        'usage': mem.percent,
    }


@router.get('/processes')
async def processes():
    res = subprocess.getoutput("ps uaxw | wc -l")
    return res


app.include_router(router, prefix=settings.PREFIX)
