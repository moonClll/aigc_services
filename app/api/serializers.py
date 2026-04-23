from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message, MessageAsset
from app.schemas.message import MessageAssetOut, MessageOut


def serialize_messages(db: Session, messages: list[Message]) -> list[dict]:
    if not messages:
        return []

    message_ids = [message.id for message in messages]
    asset_rows = db.scalars(
        select(MessageAsset)
        .where(MessageAsset.message_id.in_(message_ids))
        .order_by(MessageAsset.message_id.asc(), MessageAsset.sort_no.asc(), MessageAsset.id.asc())
    ).all()

    asset_map: dict[int, list[dict]] = defaultdict(list)
    for asset in asset_rows:
        asset_map[asset.message_id].append(MessageAssetOut.model_validate(asset).model_dump())

    result: list[dict] = []
    for message in messages:
        data = MessageOut.model_validate(message).model_dump()
        data["assets"] = asset_map.get(message.id, [])
        result.append(data)
    return result


def serialize_single_message(db: Session, message: Message) -> dict:
    rows = serialize_messages(db, [message])
    return rows[0] if rows else {}

