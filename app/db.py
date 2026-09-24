# app/db.py
import asyncio
from app.extensions import db
from prisma import Prisma

def connect_prisma():
    """Connect the shared Prisma client. Safe to call multiple times."""
    if db.is_connected():
        return
    asyncio.run(db.connect())

def disconnect_prisma():
    """Disconnect on shutdown."""
    if db.is_connected():
        asyncio.run(db.disconnect())

def run(coro):
    """
    Run an async Prisma coroutine from sync Flask code.
    Uses a fresh event loop per call — safe on Windows + Flask debug reloader.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're already inside an event loop (e.g. async route) — schedule it.
        return asyncio.ensure_future(coro)
    return asyncio.run(coro)