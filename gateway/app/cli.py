"""`python -m app.cli create-tenant NAME` prints a new tenant's admin key."""

import argparse
import asyncio

from app.config import get_settings
from app.services.tenants import create_tenant_with_key
from app.storage.db import create_all, make_engine, make_sessionmaker


async def _create(name: str) -> None:
    engine = make_engine(get_settings().database_url)
    await create_all(engine)
    t, key = await create_tenant_with_key(make_sessionmaker(engine), name)
    print(f"tenant_id={t.id}\nadmin_key={key}")
    await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(prog="spendfirewall")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-tenant")
    c.add_argument("name")
    a = p.parse_args()
    if a.cmd == "create-tenant":
        asyncio.run(_create(a.name))


if __name__ == "__main__":
    main()
