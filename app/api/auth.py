from fastapi import APIRouter, HTTPException

from app.api.deps import create_access_token, verify_password
from app.config import get_settings
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    if payload.username != settings.admin_username or not verify_password(payload.password, settings.admin_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(payload.username)
    return TokenResponse(access_token=token)
