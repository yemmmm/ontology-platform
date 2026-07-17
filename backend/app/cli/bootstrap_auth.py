from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.config import Settings
from app.repositories.models import ApiKeyModel, UserModel
from app.repositories.postgres import create_session_factory
from app.security.auth import create_api_key, hash_password


def provision_operator(
    *,
    username: str,
    password: str,
    output_path: Path,
    settings: Settings,
) -> Path:
    output_path = output_path.resolve()
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output_path.parent, 0o700)
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        factory = create_session_factory(settings)
        with factory() as session:
            user = session.scalar(select(UserModel).where(UserModel.username == username))
            if user is None:
                user = UserModel(
                    id=str(uuid4()),
                    username=username,
                    password_hash=hash_password(password),
                    session_version=1,
                )
                session.add(user)
                session.commit()
            existing = session.scalar(
                select(ApiKeyModel).where(ApiKeyModel.name == "operator-admin")
            )
            if existing is not None:
                raise RuntimeError("operator-admin API key already exists")
            record, plaintext = create_api_key(
                session,
                name="operator-admin",
                project_id=None,
                scopes=["admin"],
            )
        payload = {
            "username": username,
            "password": password,
            "api_key_id": record.id,
            "api_key": plaintext,
        }
        os.write(descriptor, json.dumps(payload, indent=2).encode("utf-8"))
    except Exception:
        os.close(descriptor)
        output_path.unlink(missing_ok=True)
        raise
    else:
        os.close(descriptor)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision the persistent R-008 operator identity")
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".local/ontology-platform-bootstrap.json"),
    )
    args = parser.parse_args()
    password = getpass.getpass("Operator password: ")
    confirmation = getpass.getpass("Confirm operator password: ")
    if not password or password != confirmation:
        raise SystemExit("Passwords are empty or do not match")
    output = provision_operator(
        username=args.username,
        password=password,
        output_path=args.output,
        settings=Settings(),
    )
    print(f"Operator credentials written to {output}")


if __name__ == "__main__":
    main()
