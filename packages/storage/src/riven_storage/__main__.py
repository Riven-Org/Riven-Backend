"""Create the artifacts bucket if it does not exist: `python -m riven_storage`."""

import asyncio

from riven_storage import ObjectStore


async def main() -> None:
    store = ObjectStore()
    await store.ensure_bucket()
    print(f"Bucket '{store.bucket}' ready")


if __name__ == "__main__":
    asyncio.run(main())
