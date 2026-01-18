import os

from app.db import models
from app.db.session import SessionLocal


def main() -> None:
    email = os.getenv("OWNER_BOOTSTRAP_EMAIL")
    uid = os.getenv("OWNER_BOOTSTRAP_UID")
    if not email:
        raise SystemExit("OWNER_BOOTSTRAP_EMAIL nao definido.")
    email = email.strip().lower()

    db = SessionLocal()
    try:
        owner = db.query(models.Owner).filter(models.Owner.email == email).first()
        if not owner:
            owner = models.Owner(email=email, uid=uid, status="ACTIVE")
            db.add(owner)
        else:
            owner.uid = uid or owner.uid
            owner.status = "ACTIVE"
        db.commit()
        print(f"Owner ACTIVE: {owner.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
