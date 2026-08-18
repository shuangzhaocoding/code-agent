from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import base64

from code_agent.config import settings


def _key_path() -> Path:
    return settings.data_dir.parent / "master.key"


def _fernet() -> Fernet:
    env = os.environ.get("CODE_AGENT_MASTER_KEY")
    if env:
        try:
            return Fernet(env.encode())
        except ValueError:
            derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"code-agent", info=b"fernet").derive(env.encode())
            return Fernet(base64.urlsafe_b64encode(derived))
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return Fernet(path.read_bytes().strip())
    key = Fernet.generate_key()
    path.write_bytes(key)
    os.chmod(path, 0o600)
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""


def mask_secret(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) <= 4:
        return "****"
    return f"****{plain[-4:]}"
