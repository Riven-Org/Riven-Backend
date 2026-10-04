from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.config import get_settings
from riven_api.db import get_session
from riven_api.models import User
from riven_api.security import create_token, hash_password, read_token, verify_password

router = APIRouter(prefix="/v1", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

Session = Annotated[AsyncSession, Depends(get_session)]


class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LogIn(BaseModel):
    # An email, or the development account's username. `email` is accepted for older clients.
    identifier: str = Field(validation_alias=AliasChoices("identifier", "email"), min_length=1)
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    created_at: datetime


class AuthResult(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


async def current_user(
    session: Session,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    user_id = read_token(creds.credentials) if creds else None
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _result(user: User) -> AuthResult:
    return AuthResult(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignUp, session: Session) -> AuthResult:
    email = body.email.lower()
    if await session.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    return _result(user)


@router.post("/auth/login")
async def login(body: LogIn, session: Session) -> AuthResult:
    email = body.identifier.strip().lower()
    settings = get_settings()
    if settings.demo_user_active and email == settings.demo_username.lower():
        email = settings.demo_email.lower()
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return _result(user)


@router.get("/me")
async def me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    return UserOut.model_validate(user)
