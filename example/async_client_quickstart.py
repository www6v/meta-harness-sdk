#!/usr/bin/env python3
"""Minimal AsyncOMAClient quickstart (Anthropic AsyncAnthropic-aligned DX).

Requires a running oma-platform::

    OMA_API_KEY=dev-key python example/async_client_quickstart.py
"""

from __future__ import annotations

import asyncio
import os

from sdk import AsyncOMAClient

OMA_BASE_URL = os.getenv("OMA_BASE_URL", "http://127.0.0.1:8787")
os.environ.setdefault("OMA_API_KEY", "dev-key")


async def main() -> None:
    async with AsyncOMAClient(base_url=OMA_BASE_URL) as client:
        models = await client.models.list()
        print("models keys:", sorted(models.keys()))
        me = await client.me.get()
        print("me user id:", (me.get("user") or {}).get("id"))


if __name__ == "__main__":
    asyncio.run(main())
