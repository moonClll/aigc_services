from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.backend import router as backend_router
from app.api.routes.callbacks import router as callback_router
from app.api.routes.conversations import router as conversation_router
from app.api.routes.learning import router as learning_router
from app.api.routes.messages import router as message_router
from app.api.routes.tasks import router as task_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(backend_router)
api_router.include_router(conversation_router)
api_router.include_router(learning_router)
api_router.include_router(message_router)
api_router.include_router(callback_router)
api_router.include_router(task_router)
