from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

async def main(url: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://127.0.0.1:8000/assess", json={"url": url})
        try:
            data = resp.json()
        except Exception:
            print(resp.status_code, resp.text)
            return
        output = json.dumps(data, indent=2, ensure_ascii=False)
        Path("tmp/devclient.json").write_text(output, encoding="utf-8")
        print(output)

if __name__ == "main":
    raise SystemExit("Run via `python -m backend.api.devclient <url>`. ")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m backend.api.devclient <url>")
    asyncio.run(main(sys.argv[1]))
