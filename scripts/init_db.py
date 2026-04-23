from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models import Base, User

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "Demo@123456"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existed = db.scalar(select(User).where(User.username == DEMO_USERNAME))
        if existed is None:
            user = User(
                username=DEMO_USERNAME,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="Demo User",
                status="active",
            )
            db.add(user)
            db.commit()
            print(f"Demo user created: {DEMO_USERNAME} / {DEMO_PASSWORD}")
        else:
            print("Demo user already exists.")

    print("Database initialization finished.")


if __name__ == "__main__":
    main()
