from fastapi import APIRouter

from app.core.security import User

router = APIRouter()


@router.get("/me")
async def me(user: User) -> dict:
    # Memberships are added with the workspaces module (M2).
    return {"id": user.id, "email": user.email, "name": user.name, "memberships": []}
