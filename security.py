# security.py
import os
from cryptography.fernet import Fernet

# ⚠️ IN PRODUCTION: Set this environment variable in your server.
# To generate a key run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SECRET_ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

cipher_suite = Fernet(SECRET_ENCRYPTION_KEY.encode())

def encrypt_key(api_key: str) -> str:
    """Encrypts a plaintext API key."""
    if not api_key:
        return ""
    return cipher_suite.encrypt(api_key.encode()).decode()

def decrypt_key(encrypted_key: str) -> str:
    """Decrypts an encrypted API key back to plaintext."""
    if not encrypted_key:
        return ""
    return cipher_suite.decrypt(encrypted_key.encode()).decode()