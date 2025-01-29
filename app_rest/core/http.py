import aiohttp

from .utils import singleton


@singleton
async def get_http_session():
    session = aiohttp.ClientSession()
    return session
