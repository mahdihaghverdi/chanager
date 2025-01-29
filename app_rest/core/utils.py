import asyncio
import functools
import inspect
import threading


def singleton(fun):
    """Thread and Coroutine Safe Singleton Decorator"""
    sentinel = instance = object()
    lock = asyncio.Lock()
    sync_lock = threading.Lock()

    @functools.wraps(fun)
    async def async_wrapper(*args, **kwargs):
        nonlocal instance
        if instance is sentinel:
            async with lock:
                if instance is sentinel:
                    instance = await fun(*args, **kwargs)
        return instance

    @functools.wraps(fun)
    def sync_wrapper(*args, **kwargs):
        nonlocal instance
        if instance is sentinel:
            with sync_lock:
                if instance is sentinel:
                    instance = fun(*args, **kwargs)
        return instance

    if inspect.iscoroutinefunction(fun):
        return async_wrapper
    return sync_wrapper
