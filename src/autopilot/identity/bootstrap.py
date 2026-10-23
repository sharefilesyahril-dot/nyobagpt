"""One-time administrative owner bootstrap; never exposed as HTTP."""

import argparse

from sqlalchemy.orm import Session

from autopilot.db import get_engine
from autopilot.identity.service import bootstrap_owner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret", required=True, help="Administrative bootstrap secret")
    args = parser.parse_args()
    with Session(get_engine(), expire_on_commit=False) as session:
        actor, credential = bootstrap_owner(session, args.secret)
        session.commit()
    print(f"Owner ID: {actor.id}")
    print(f"Owner bearer credential (store securely; shown once): {credential}")


if __name__ == "__main__":
    main()
