"""Small password and bearer-session service backed by the platform database."""
from __future__ import annotations

from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid

from .database import AuthSession, DatabaseManager, User

PBKDF2_ITERATIONS = 600_000
SESSION_DAYS = 30
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, database_url: str):
        self.db = DatabaseManager(database_url)
        self.db.create_tables()

    def register(self, username: str, email: str, password: str):
        username, email = username.strip(), email.strip().lower()
        if not 2 <= len(username) <= 40:
            raise ValueError("Display name must contain 2–40 characters")
        if not EMAIL.match(email) or len(email) > 254:
            raise ValueError("Enter a valid email address")
        if len(password) < 10 or len(password) > 256:
            raise ValueError("Password must contain at least 10 characters")
        with self.db as session:
            if session.query(User).filter((User.email == email) | (User.username == username)).first():
                raise ValueError("That email or display name is already registered")
            user = User(id=f"user-{uuid.uuid4().hex}", username=username, email=email,
                        password_hash=hash_password(password))
            session.add(user)
            session.flush()
            result = user.to_dict()
        token = self._new_session(result["user_id"])
        return result, token

    def login(self, email: str, password: str):
        with self.db as session:
            user = session.query(User).filter(User.email == email.strip().lower(), User.is_active.is_(True)).first()
            if user is None or not verify_password(password, user.password_hash):
                raise ValueError("Email or password is incorrect")
            result = user.to_dict()
        return result, self._new_session(result["user_id"])

    def _new_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(48)
        with self.db as session:
            session.add(AuthSession(id=f"session-{uuid.uuid4().hex}", user_id=user_id,
                                    token_hash=token_hash(token),
                                    expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS)))
        return token

    def user_for_token(self, token: str | None):
        if not token:
            return None
        with self.db as session:
            auth_session = session.query(AuthSession).filter(
                AuthSession.token_hash == token_hash(token), AuthSession.expires_at > datetime.utcnow()
            ).first()
            return auth_session.user.to_dict() if auth_session and auth_session.user.is_active else None

    def logout(self, token: str) -> None:
        with self.db as session:
            session.query(AuthSession).filter(AuthSession.token_hash == token_hash(token)).delete()

