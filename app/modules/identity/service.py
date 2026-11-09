"""Identity operations. Session values stored in the database are hashes."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pwdlib import PasswordHash
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.identity.models import LoginSession, User

passwords = PasswordHash.recommended()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register(db: Session, username: str, password: str, display_name: str) -> User:
    username = username.strip().lower()
    display_name = display_name.strip()
    if not (3 <= len(username) <= 64 and username.isascii() and all(c.isalnum() or c in "_.-" for c in username)):
        raise ValueError("用户名须为 3–64 位英文字母、数字或 _.-")
    if not 10 <= len(password) <= 128:
        raise ValueError("密码须为 10–128 个字符")
    if not 1 <= len(display_name) <= 80:
        raise ValueError("昵称须为 1–80 个字符")
    # Serializes the first-user check in PostgreSQL without a separate table.
    db.execute(text("SELECT pg_advisory_xact_lock(701131)"))
    if db.scalar(select(User.id).limit(1)) is not None:
        raise ValueError("本地单用户账号已创建，请登录")
    user = User(username=username, password_hash=passwords.hash(password), display_name=display_name, timezone="Asia/Shanghai")
    db.add(user)
    db.flush()
    return user


def login(db: Session, username: str, password: str) -> str:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or not passwords.verify(password, user.password_hash):
        raise ValueError("用户名或密码不正确")
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    return token


def current_user(db: Session, token: str | None) -> User | None:
    if not token or len(token) > 128:
        return None
    return db.scalar(select(User).join(LoginSession, LoginSession.user_id == User.id).where(
        LoginSession.token_hash == token_hash(token), LoginSession.expires_at > datetime.now(timezone.utc)))


def update_profile(user: User, display_name: str, timezone_name: str) -> None:
    display_name = display_name.strip()
    if not 1 <= len(display_name) <= 80:
        raise ValueError("昵称须为 1–80 个字符")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("请输入有效时区，例如 Asia/Shanghai") from None
    user.display_name = display_name
    user.timezone = timezone_name
