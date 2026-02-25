import base64
import os
from hashlib import sha256

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _build_aes_key() -> bytes:
    """
    Derive a 256-bit key from ENCRYPTION_KEY.
    If ENCRYPTION_KEY is already 32 raw bytes (base64 or hex), we try to decode it.
    Otherwise we hash the string with SHA-256.
    """
    raw = os.getenv("ENCRYPTION_KEY")
    if not raw:
        # Dev fallback – in production you MUST set ENCRYPTION_KEY explicitly.
        raw = "dev-only-change-me"

    # Try base64
    try:
        key = base64.b64decode(raw)
        if len(key) == 32:
            return key
    except Exception:
        pass

    # Try hex
    try:
        key = bytes.fromhex(raw)
        if len(key) == 32:
            return key
    except Exception:
        pass

    # Fallback: derive from UTF‑8 string via SHA-256 (32 bytes).
    return sha256(raw.encode("utf-8")).digest()


_AES_KEY = _build_aes_key()


def encrypt_key(api_key: str) -> str:
    """
    Encrypts a plaintext API key using AES-256-GCM.
    Returns a base64 string containing nonce + ciphertext + tag.
    """
    if not api_key:
        return ""

    aesgcm = AESGCM(_AES_KEY)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, api_key.encode("utf-8"), None)
    blob = nonce + ct
    return base64.b64encode(blob).decode("utf-8")


def decrypt_key(encrypted_key: str) -> str:
    """
    Decrypts an AES-256-GCM encrypted API key produced by encrypt_key.
    """
    if not encrypted_key:
        return ""

    aesgcm = AESGCM(_AES_KEY)
    blob = base64.b64decode(encrypted_key.encode("utf-8"))
    nonce, ct = blob[:12], blob[12:]
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")