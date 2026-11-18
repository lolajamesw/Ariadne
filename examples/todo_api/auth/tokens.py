import jwt
from db.models import User


def require_user(token: str) -> User:
    if not token:
        raise PermissionError("missing token")
    return User()
