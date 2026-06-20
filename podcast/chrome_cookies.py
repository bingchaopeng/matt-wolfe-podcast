"""
Chrome cookies export module.
Extracts YouTube cookies from Chrome's encrypted cookie database
and writes them in Netscape cookie file format compatible with yt-dlp.
Works when Chrome is closed (copies the database, then decrypts via win32crypt).
"""

import base64
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CHROME_USER_DATA = os.path.expanduser(
    "~/AppData/Local/Google/Chrome/User Data"
)
COOKIES_DB_REL = "Default/Network/Cookies"
LOCAL_STATE_PATH = "Local State"


def _get_encryption_key() -> bytes | None:
    """Read and decrypt the Chrome encryption key from Local State."""
    ls_path = os.path.join(CHROME_USER_DATA, LOCAL_STATE_PATH)
    if not os.path.isfile(ls_path):
        logger.warning("Chrome Local State not found: %s", ls_path)
        return None
    try:
        with open(ls_path, encoding="utf-8") as f:
            ls = json.load(f)
        enc_key_b64 = ls.get("os_crypt", {}).get("encrypted_key")
        if not enc_key_b64:
            logger.warning("No encrypted_key in Local State")
            return None
        from win32crypt import CryptUnprotectData
        encrypted = base64.b64decode(enc_key_b64)
        # Chrome prepends 'DPAPI' (5 bytes) to the encrypted key
        _, key = CryptUnprotectData(encrypted[5:], None, None, None, 0)
        logger.info("Chrome encryption key decrypted (%d bytes)", len(key))
        return key
    except Exception as exc:
        logger.warning("Failed to decrypt Chrome key: %s", exc)
        return None


def _decrypt_cookie(encrypted_value: bytes, key: bytes) -> str:
    """Decrypt a Chrome cookie value using AES-GCM."""
    if not encrypted_value or encrypted_value == b"":
        return ""
    try:
        # Chrome v80+ uses AES-GCM with nonce + ciphertext + tag
        # Format: 'v10' + nonce (12 bytes) + ciphertext + tag (16 bytes)
        from Cryptodome.Cipher import AES
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode("utf-8")
    except Exception:
        # Fallback: maybe not encrypted (old cookie)
        return encrypted_value.decode("utf-8", errors="replace")


def _netscape_cookie_line(
    domain: str, name: str, value: str, path: str,
    expires: int, secure: bool, httponly: bool
) -> str:
    """Format a single cookie in Netscape HTTP Cookie File format."""
    secure_flag = "TRUE" if secure else "FALSE"
    # domain flag: TRUE if domain starts with '.'
    domain_flag = "TRUE" if domain.startswith(".") else "FALSE"
    httponly_flag = "#HttpOnly_" if httponly else ""
    return (
        f"{httponly_flag}{domain}\t{domain_flag}\t{path}\t"
        f"{secure_flag}\t{expires}\t{name}\t{value}"
    )


def export_chrome_cookies(output_path: str, target_domain: str = "youtube.com") -> bool:
    """
    Export Chrome cookies to a Netscape-format cookie file.

    Closes are read from a **copy** of the Chrome Cookies database
    so that Chrome can remain open (the copy bypasses the lock).

    Args:
        output_path: Path to write the cookies.txt file.
        target_domain: Only export cookies for this domain (default: youtube.com).

    Returns:
        True if at least one cookie was exported successfully.
    """
    # Copy the Cookies DB while Chrome may have it open
    db_path = os.path.join(CHROME_USER_DATA, COOKIES_DB_REL)
    if not os.path.isfile(db_path):
        logger.warning("Chrome cookies DB not found: %s", db_path)
        return False

    tmp_db = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(db_path, tmp_db)
    except OSError as exc:
        logger.warning("Failed to copy Chrome cookies DB: %s", exc)
        return False

    key = _get_encryption_key()
    if key is None:
        logger.error("Cannot decrypt cookies without encryption key")
        os.unlink(tmp_db)
        return False

    try:
        conn = sqlite3.connect(tmp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT host_key, name, value, path, expires_utc, "
            "is_secure, is_httponly, encrypted_value "
            "FROM cookies WHERE host_key LIKE ?",
            (f"%{target_domain}%",)
        )
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("Failed to read cookies DB: %s", exc)
        os.unlink(tmp_db)
        return False
    finally:
        if os.path.exists(tmp_db):
            os.unlink(tmp_db)

    if not rows:
        logger.warning("No cookies found for domain: %s", target_domain)
        return False

    # Chrome's expires_utc is microseconds since 1601-01-01
    WINDOWS_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)

    lines = [
        "# Netscape HTTP Cookie File",
        "# This file is auto-generated by chrome_cookies.py",
        "# https://curl.se/rfc/cookie_spec.html",
        "# Edit at your own risk.",
        "",
    ]
    count = 0
    for host_key, name, plain_value, path, expires_utc, is_secure, is_httponly, enc_value in rows:
        # Try encrypted value first, fall back to plain
        if enc_value and enc_value != b"" and enc_value != plain_value.encode() if plain_value else True:
            try:
                value = _decrypt_cookie(enc_value, key)
            except Exception:
                value = plain_value or ""
        else:
            value = plain_value or ""

        if not value:
            continue

        # Convert Chrome timestamp to Unix timestamp (seconds)
        if expires_utc and expires_utc > 0:
            try:
                delta = (datetime.now(timezone.utc) - WINDOWS_EPOCH).total_seconds()
                # Alternative: expires_utc is microseconds since 1601
                expires_unix = int((expires_utc / 1_000_000) - 11644473600)
                if expires_unix < 0:
                    expires_unix = 0
            except (ValueError, OverflowError):
                expires_unix = 0
        else:
            expires_unix = 0

        line = _netscape_cookie_line(
            host_key, name, value, path or "/",
            expires_unix, bool(is_secure), bool(is_httponly)
        )
        lines.append(line)
        count += 1

    if count == 0:
        logger.warning("No decodable cookies found for %s", target_domain)
        return False

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Exported %d cookies to %s", count, output_path)
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt")
    export_chrome_cookies(out)
