import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import DangerousActionConfirm

DANGEROUS_ACTION_PHRASE = "DELETE THIS"

# Private-conversation ownership for the no-login chat widget: a random,
# httpOnly, opaque token identifies "this browser" without ever being a staff
# identity. Only its hash is ever stored or queried — the raw token never
# leaves the cookie (not logged, not echoed in any response body).
OWNER_COOKIE_NAME = "helpdesk_owner"
OWNER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def _hash_owner_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_owner_hash(request: Request, response: Response) -> str:
    token = request.cookies.get(OWNER_COOKIE_NAME)
    if not token:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            OWNER_COOKIE_NAME,
            token,
            max_age=OWNER_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    return _hash_owner_token(token)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username = payload.get("sub")
    if username is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def require_agent_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "agent"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_dangerous_action_confirmation(
    payload: DangerousActionConfirm,
    user: User = Depends(require_admin),
) -> User:
    """Extra gate in front of bulk-delete endpoints, on top of the normal JWT
    check: the typed phrase proves intent (no more fat-fingering a single
    "Reset" button), and re-entering username+password proves it's actually
    the admin at the keyboard right now, not just a valid token from a
    session left open on someone else's screen."""
    if payload.confirm_text.strip() != DANGEROUS_ACTION_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Type "{DANGEROUS_ACTION_PHRASE}" exactly to confirm.',
        )
    if payload.username.strip().lower() != user.username.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username does not match the signed-in admin account.",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password.")
    return user
