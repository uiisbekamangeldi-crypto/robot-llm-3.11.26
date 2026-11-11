"""Explicit retention cleanup for dialog text; dry run unless --apply is supplied."""

import argparse
import asyncio

from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.resources import Infrastructure


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 3650:
        parser.error("--days must be between 1 and 3650")
    resources = Infrastructure.from_settings(get_settings())
    try:
        async with resources.engine.begin() as conn:
            params = {"days": args.days}
            count = await conn.execute(
                text("""SELECT COUNT(*) FROM dialog_turns
                     WHERE created_at < now() - make_interval(days => :days)"""),
                params,
            )
            print(f"Old dialog turns: {count.scalar_one()}")
            if args.apply:
                await conn.execute(
                    text("""DELETE FROM dialog_turns
                         WHERE created_at < now() - make_interval(days => :days)"""),
                    params,
                )
                await conn.execute(
                    text("""DELETE FROM dialog_sessions s WHERE NOT EXISTS
                         (SELECT 1 FROM dialog_turns t WHERE t.session_id = s.id)""")
                )
                print("Old dialog turns deleted")
    finally:
        await resources.close()


if __name__ == "__main__":
    asyncio.run(main())
