"""Explicit administrator provisioning; never runs during server startup."""
import argparse
import asyncio
import getpass
from sqlalchemy import select
from auth import get_password_hash
from database import AsyncSessionLocal, engine
from models import AdminUser


async def provision(username: str, reset: bool):
    password = getpass.getpass("New administrator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation or len(password) < 12 or len(password.encode()) > 72:
        raise SystemExit("Passwords must match and contain 12–72 UTF-8 bytes")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(AdminUser).where(AdminUser.username == username))).scalar_one_or_none()
        if user and not reset:
            raise SystemExit("Administrator exists. Use --reset only for an authorized password change")
        if user:
            user.hashed_password = get_password_hash(password)
        else:
            session.add(AdminUser(username=username, hashed_password=get_password_hash(password), role="admin", is_active=True))
        await session.commit()
    await engine.dispose()
    print("Administrator credentials saved. Existing sessions are invalidated by credential fingerprint.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if not args.username.strip() or len(args.username) > 50:
        raise SystemExit("A valid administrator username is required")
    asyncio.run(provision(args.username.strip(), args.reset))
