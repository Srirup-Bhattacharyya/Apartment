from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Role, Settings, User
from .security import hash_password


MEMBERS = [
    ("Adhir Das", "adhir.das", 460),
    ("Bipul Ghosh", "bipul.ghosh", 1780),
    ("Debabrata Basu", "debabrata.basu", 2760),
    ("Bharati Chakraborty", "bharati.chakraborty", 570),
    ("Sudip Bhattacharyya", "sudip.bhattacharyya", 680),
    ("Subhankar Chandra", "subhankar.chandra", 570),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        if db.scalar(select(User).where(User.username == "Manager")):
            return
        db.add(User(name="Sudip Bhattacharyya", username="Manager", password_hash=hash_password("Manager@2026"), role=Role.MANAGER, wallet_balance=50000))
        db.add_all(
            User(name=name, username=username, password_hash=hash_password("welcome1"), role=Role.MEMBER, outstanding_due=due)
            for name, username, due in MEMBERS
        )
        db.add(Settings(id=1, monthly_fee=460, billing_month="November 2026"))


if __name__ == "__main__":
    seed()
