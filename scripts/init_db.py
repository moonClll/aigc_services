from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.mock_user_profile import pick_mock_user_profile
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
            mock_profile = pick_mock_user_profile(DEMO_USERNAME)
            user = User(
                username=DEMO_USERNAME,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name=mock_profile["display_name"],
                avatar_url=mock_profile["avatar_url"],
                status="active",
            )
            db.add(user)
            db.commit()
            print(f"Demo user created: {DEMO_USERNAME} / {DEMO_PASSWORD}")
        else:
            changed = False
            if not existed.display_name or not existed.avatar_url:
                mock_profile = pick_mock_user_profile(DEMO_USERNAME)
                existed.display_name = mock_profile["display_name"]
                existed.avatar_url = mock_profile["avatar_url"]
                changed = True
            if changed:
                db.add(existed)
                db.commit()
                print("Demo user profile updated from mock data.")
            print("Demo user already exists.")

    print("Database initialization finished.")


if __name__ == "__main__":
    main()
