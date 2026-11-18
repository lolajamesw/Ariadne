from fastapi import APIRouter, HTTPException
from services.tasks import TaskService
from auth.tokens import require_user

router = APIRouter()
service = TaskService()


@router.post("/tasks")
def create_task(title: str, token: str):
    user = require_user(token)
    if not title:
        raise HTTPException(400, "title required")
    return service.create(user, title)
