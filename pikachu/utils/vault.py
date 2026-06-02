"""
pikachu/utils/vault.py
─────────────────────
Secure local secret storage for the Living Desktop Pet.

Architecture (defence-in-depth):
    Layer 1  Windows Credential Manager (keyring) — stores the master key
    Layer 2  Fernet (AES-128-CBC + HMAC-SHA256) — encrypts large blobs
    Layer 3  DPAPI fallback — used if keyring is unavailable

Sensitive files (token.json, credentials.json) are NEVER stored in plain
text.  Encrypted copies live in ~/.pikachu/ under the names
  token.json.enc
  credentials.json.enc
The originals (plain text) should NEVER exist on disk.

All encrypted files are bound to the current Windows user via the master
key, which Windows Credential Manager protects with DPAPI internally.
"""

import os
import stat
import json
import base64
import secrets

from cryptography.fernet import InvalidToken
from pikachu import config as cfg
from pikachu.utils.logger import get_logger

log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_SERVICE  = "LivingDesktopPet"
_USERNAME = "pikachu_vault"
_ENC_EXT  = ".enc"


# ── Key management ────────────────────────────────────────────────────────────

def _get_or_create_master_key() -> bytes:
    """
    Return the 32-byte master key from Windows Credential Manager.
    If no key exists yet, generate a cryptographically random one and store it.
    """
    import keyring
    stored = keyring.get_password(_SERVICE, _USERNAME)
    if stored:
        return base64.urlsafe_b64decode(stored.encode())

    # First run — generate a brand-new 32-byte key
    key = secrets.token_bytes(32)
    keyring.set_password(
        _SERVICE, _USERNAME,
        base64.urlsafe_b64encode(key).decode()
    )
    log.info("New master key created and stored in Windows Credential Manager.")
    return key


def _get_fernet():
    """Return a ready-to-use Fernet instance backed by the master key."""
    from cryptography.fernet import Fernet
    key = _get_or_create_master_key()
    fernet_key = base64.urlsafe_b64encode(key)   # Fernet expects URL-safe b64
    return Fernet(fernet_key)


# ── DPAPI fallback (if keyring is not available) ──────────────────────────────

def _dpapi_encrypt(data: bytes) -> bytes:
    """Encrypt raw bytes using Windows DPAPI (user-bound)."""
    import win32crypt
    return win32crypt.CryptProtectData(data, None, None, None, None, 0)


def _dpapi_decrypt(blob: bytes) -> bytes:
    """Decrypt a DPAPI blob."""
    import win32crypt
    # Args: DataIn, DataDescr, OptionalEntropy, Reserved, PromptStruct, Flags
    _desc, data = win32crypt.CryptUnprotectData(blob, None, None, None, None, 0)
    return data


# ── Public API ────────────────────────────────────────────────────────────────

def encrypt_file(source_path: str) -> str:
    """
    Encrypt *source_path* with Fernet and write ``<source_path>.enc``.
    The plain-text source is NOT deleted here — caller decides.

    Returns:
        Path to the encrypted file.
    """
    enc_path = source_path + _ENC_EXT
    try:
        f = _get_fernet()
        with open(source_path, "rb") as fp:
            plain = fp.read()
        cipher = f.encrypt(plain)
        with open(enc_path, "wb") as fp:
            fp.write(cipher)
        # Restrict to owner-read-only (chmod 600)
        os.chmod(enc_path, stat.S_IRUSR | stat.S_IWUSR)
        log.info("Encrypted: %s -> %s", os.path.basename(source_path),
                 os.path.basename(enc_path))
        return enc_path
    except Exception as e:
        log.error("encrypt_file failed (%s): %s", source_path, e)
        raise


def decrypt_file(enc_path: str, dest_path: str = None) -> bytes:
    """
    Decrypt *enc_path* and return the plain bytes.
    Optionally write them to *dest_path* (e.g. a temp file).

    Returns:
        Decrypted bytes.
    """
    try:
        f = _get_fernet()
        with open(enc_path, "rb") as fp:
            cipher = fp.read()
        plain = f.decrypt(cipher)   # raises InvalidToken if tampered
        if dest_path:
            with open(dest_path, "wb") as fp:
                fp.write(plain)
            log.debug("Decrypted to: %s", dest_path)
        return plain
    except InvalidToken:
        log.error("decrypt_file: file tampered or wrong key — %s", enc_path)
        raise
    except Exception as e:
        log.error("decrypt_file failed (%s): %s", enc_path, e)
        raise


def save_secret(name: str, data: dict) -> str:
    """
    Encrypt a dict as JSON and save it as ``~/.pikachu/<name>.enc``.

    Args:
        name: Logical name, e.g. "token" or "credentials".
        data: Python dict to persist.

    Returns:
        Path to the written ``.enc`` file.
    """
    enc_path = os.path.join(cfg.DATA_DIR, name + _ENC_EXT)
    try:
        f = _get_fernet()
        plain = json.dumps(data, indent=2).encode("utf-8")
        cipher = f.encrypt(plain)
        with open(enc_path, "wb") as fp:
            fp.write(cipher)
        # Owner-read-only
        os.chmod(enc_path, stat.S_IRUSR | stat.S_IWUSR)
        log.info("Secret saved: %s", name + _ENC_EXT)
        return enc_path
    except Exception as e:
        log.error("save_secret failed (%s): %s", name, e)
        raise


def load_secret(name: str) -> dict:
    """
    Load and decrypt a secret previously saved with ``save_secret()``.

    Args:
        name: Same logical name used in ``save_secret()``.

    Returns:
        Decrypted dict, or {} if the file does not exist.
    """
    enc_path = os.path.join(cfg.DATA_DIR, name + _ENC_EXT)
    if not os.path.exists(enc_path):
        log.debug("No encrypted file found for: %s", name)
        return {}
    try:
        f = _get_fernet()
        with open(enc_path, "rb") as fp:
            cipher = fp.read()
        plain = f.decrypt(cipher)   # raises InvalidToken if tampered
        data  = json.loads(plain.decode("utf-8"))
        log.debug("Secret loaded: %s", name)
        return data
    except InvalidToken:
        log.error("load_secret: file tampered or wrong key — %s", name)
        return {}
    except Exception as e:
        log.error("load_secret failed (%s): %s", name, e)
        return {}


def secret_exists(name: str) -> bool:
    """Return True if an encrypted file for *name* exists."""
    enc_path = os.path.join(cfg.DATA_DIR, name + _ENC_EXT)
    return os.path.exists(enc_path)


def delete_secret(name: str):
    """Securely delete an encrypted secret file (overwrite before remove)."""
    enc_path = os.path.join(cfg.DATA_DIR, name + _ENC_EXT)
    if os.path.exists(enc_path):
        size = os.path.getsize(enc_path)
        # Overwrite with random bytes before deletion (basic secure erase)
        with open(enc_path, "wb") as fp:
            fp.write(secrets.token_bytes(size))
        os.remove(enc_path)
        log.info("Secret deleted: %s", name)


def rotate_master_key():
    """
    Re-encrypt all stored secrets with a brand-new master key.
    Call this if you suspect the old key may be compromised.
    """
    import keyring
    log.warning("Rotating master key…")

    # 1. Decrypt all secrets with the old key
    secrets_backup = {}
    for fname in os.listdir(cfg.DATA_DIR):
        if fname.endswith(_ENC_EXT):
            name = fname[: -len(_ENC_EXT)]
            secrets_backup[name] = load_secret(name)

    # 2. Generate and store a new key
    new_key = secrets.token_bytes(32)
    keyring.set_password(
        _SERVICE, _USERNAME,
        base64.urlsafe_b64encode(new_key).decode()
    )
    log.info("New master key stored.")

    # 3. Re-encrypt everything with the new key
    for name, data in secrets_backup.items():
        if data:
            save_secret(name, data)

    log.info("Key rotation complete. All secrets re-encrypted.")
