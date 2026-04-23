from pathlib import Path
import sys

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import engine
from app.models import Base


def _ensure_generation_task_columns() -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("generation_tasks")}
    statements: list[str] = []

    if "worker_id" not in columns:
        statements.append("ALTER TABLE generation_tasks ADD COLUMN worker_id VARCHAR(64) NULL;")
    if "dispatch_attempts" not in columns:
        statements.append(
            "ALTER TABLE generation_tasks ADD COLUMN dispatch_attempts INT NOT NULL DEFAULT 0;"
        )
    if "claimed_at" not in columns:
        statements.append("ALTER TABLE generation_tasks ADD COLUMN claimed_at DATETIME NULL;")
    if "lease_expires_at" not in columns:
        statements.append(
            "ALTER TABLE generation_tasks ADD COLUMN lease_expires_at DATETIME NULL;"
        )
    if "answer_message_id" not in columns:
        statements.append("ALTER TABLE generation_tasks ADD COLUMN answer_message_id BIGINT NULL;")
    if "replace_answer_message_id" not in columns:
        statements.append(
            "ALTER TABLE generation_tasks ADD COLUMN replace_answer_message_id BIGINT NULL;"
        )
    if "feedback_id" not in columns:
        statements.append("ALTER TABLE generation_tasks ADD COLUMN feedback_id BIGINT NULL;")

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))

    foreign_keys = inspector.get_foreign_keys("generation_tasks")
    fk_columns = {
        tuple((fk.get("constrained_columns") or []))
        for fk in foreign_keys
    }

    fk_statements: list[str] = []
    if ("answer_message_id",) not in fk_columns:
        fk_statements.append(
            "ALTER TABLE generation_tasks "
            "ADD CONSTRAINT fk_generation_tasks_answer_message "
            "FOREIGN KEY (answer_message_id) REFERENCES messages(id) ON DELETE SET NULL;"
        )
    if ("replace_answer_message_id",) not in fk_columns:
        fk_statements.append(
            "ALTER TABLE generation_tasks "
            "ADD CONSTRAINT fk_generation_tasks_replace_answer_message "
            "FOREIGN KEY (replace_answer_message_id) REFERENCES messages(id) ON DELETE SET NULL;"
        )
    if ("feedback_id",) not in fk_columns:
        fk_statements.append(
            "ALTER TABLE generation_tasks "
            "ADD CONSTRAINT fk_generation_tasks_feedback "
            "FOREIGN KEY (feedback_id) REFERENCES feedbacks(id) ON DELETE SET NULL;"
        )
    with engine.begin() as conn:
        for sql in fk_statements:
            conn.execute(text(sql))


def _ensure_generation_task_indexes() -> None:
    inspector = inspect(engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("generation_tasks")}
    statements: list[str] = []

    if "ix_generation_tasks_worker_id" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_worker_id ON generation_tasks (worker_id);"
        )
    if "ix_generation_tasks_claimed_at" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_claimed_at ON generation_tasks (claimed_at);"
        )
    if "ix_generation_tasks_lease_expires_at" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_lease_expires_at ON generation_tasks (lease_expires_at);"
        )
    if "ix_generation_tasks_answer_message_id" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_answer_message_id ON generation_tasks (answer_message_id);"
        )
    if "ix_generation_tasks_status_lease" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_status_lease ON generation_tasks (status, lease_expires_at);"
        )
    if "ix_generation_tasks_replace_answer_message_id" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_replace_answer_message_id "
            "ON generation_tasks (replace_answer_message_id);"
        )
    if "ix_generation_tasks_feedback_id" not in indexes:
        statements.append(
            "CREATE INDEX ix_generation_tasks_feedback_id ON generation_tasks (feedback_id);"
        )

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def main() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_generation_task_columns()
    _ensure_generation_task_indexes()
    print("Latest schema upgrade finished.")


if __name__ == "__main__":
    main()
