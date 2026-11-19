"""Codigos de verificacion en dos pasos (TOTP, RFC 6238), compatibles con Google Authenticator,
Microsoft Authenticator, Authy, 1Password, etc. Sin dependencias externas."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code_for(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 10 ** DIGITS:0{DIGITS}d}"


def verify(secret, code, last_counter=0, at=None, window=1):
    """Devuelve el contador del codigo aceptado, o None. Un codigo ya usado (contador <= last_counter) se rechaza."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    now_counter = int((at if at is not None else time.time()) // STEP)
    for counter in range(now_counter - window, now_counter + window + 1):
        if counter > last_counter and hmac.compare_digest(_code_for(secret, counter), code):
            return counter
    return None


def provisioning_uri(secret, account, issuer="Tengo Stock"):
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
