from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.internal_auth import verify_internal_token
from app.core.database import get_db
from app.core.response import ok
from app.core.task_result_service import store_model_answer, store_model_failure
from app.schemas.message import ModelAnswerCallbackIn
from app.schemas.task import GenerationTaskOut, ModelFailureCallbackIn

router = APIRouter(prefix="/callbacks", tags=["Callbacks"])


@router.post("/model-answer")
def receive_model_answer(
    payload: ModelAnswerCallbackIn,
    _token_guard: None = Depends(verify_internal_token),
    db: Session = Depends(get_db),
) -> dict:
    data = store_model_answer(db, payload)
    return ok(data, "Answer stored")


@router.post("/model-failure")
def receive_model_failure(
    payload: ModelFailureCallbackIn,
    _token_guard: None = Depends(verify_internal_token),
    db: Session = Depends(get_db),
) -> dict:
    task = store_model_failure(db, payload)
    return ok(GenerationTaskOut.model_validate(task).model_dump(), "Failure stored")

