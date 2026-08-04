from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sawtai.auth.service import DEMO_TOKEN, UserContext, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/token")
async def token(payload: LoginRequest) -> dict[str, object]:
    if payload.email != "demo@sawtai.ae" or payload.password != "demo":
        raise HTTPException(status_code=401, detail="Invalid demo credentials")
    return {"access_token": DEMO_TOKEN, "token_type": "bearer", "expires_in": 1800}


@router.get("/me")
async def me(user: UserContext = Depends(get_current_user)) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "display_name_ar": user.display_name_ar,
        "display_name_en": user.display_name_en,
        "roles": user.roles,
        "permissions": sorted(user.permissions),
    }
