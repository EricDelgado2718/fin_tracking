import json
from datetime import date

from cryptography.fernet import Fernet, InvalidToken

from . import config


def _fernet():
    key = config.FERNET_KEY
    if not key:
        raise RuntimeError("FERNET_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def load_tokens():
    path = config.tokens_path()
    if not path.exists():
        return {}
    blob = path.read_bytes()
    if not blob:
        return {}
    try:
        decrypted = _fernet().decrypt(blob)
    except InvalidToken as e:
        raise RuntimeError(
            "Failed to decrypt tokens.enc — FERNET_KEY does not match the key used to encrypt it"
        ) from e
    return json.loads(decrypted.decode("utf-8"))


def _write(tokens):
    path = config.tokens_path()
    payload = json.dumps(tokens, sort_keys=True).encode("utf-8")
    path.write_bytes(_fernet().encrypt(payload))


def save_token(institution, access_token, item_id, linked_at=None):
    tokens = load_tokens()
    tokens[institution] = {
        "access_token": access_token,
        "item_id": item_id,
        "linked_at": linked_at or date.today().isoformat(),
    }
    _write(tokens)


def delete_token(institution):
    tokens = load_tokens()
    if institution in tokens:
        del tokens[institution]
        _write(tokens)
