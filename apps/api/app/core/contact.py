"""Phone numbers and e-mail addresses given by the public (« Me prévenir », the SMS line).

They are never stored in clear: lookups use an HMAC of the normalised contact (keyed from
`SEAL_SECRET`), screens show a masked form (« +261 34 •• ••• 12 »), and the one copy needed to
send the answer later is sealed with Fernet under the same secret. Without the secret nothing is
accepted (503), rather than storing a hash anyone could reverse by trying every number.
"""

import base64
import hashlib
import hmac
import re
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import ApiError

Kind = Literal["phone", "email"]
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.IGNORECASE)


def _secret() -> bytes:
    secret = get_settings().seal_secret
    if not secret:
        raise ApiError(
            503, "contact_protection_unavailable", "Contacts cannot be protected right now"
        )
    return secret.encode()


def configured() -> bool:
    return bool(get_settings().seal_secret)


def normalise(contact: str) -> tuple[Kind, str]:
    """('phone', '+261340000012') or ('email', 'name@example.org'); ValueError otherwise.
    A Malagasy mobile number written the national way (034 00 000 12) gets its +261."""
    value = (contact or "").strip()
    if "@" in value:
        if not EMAIL.match(value):
            raise ValueError("not an e-mail address")
        return "email", value.lower()
    digits = re.sub(r"[\s.\-()/]", "", value)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if re.fullmatch(r"03[2-9]\d{7}", digits):
        digits = "+261" + digits[1:]
    if not re.fullmatch(r"\+?\d{8,15}", digits):
        raise ValueError("not a phone number")
    return "phone", digits if digits.startswith("+") else "+" + digits


def digest(kind: Kind, value: str) -> str:
    key = hashlib.sha256(b"checky-contact-hash|" + _secret()).digest()
    return hmac.new(key, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def mask(kind: Kind, value: str) -> str:
    if kind == "email":
        name, _, domain = value.partition("@")
        return f"{name[:1]}•••@{domain}"
    if value.startswith("+261") and len(value) == 13:
        return f"+261 {value[4:6]} •• ••• {value[-2:]}"
    return f"{value[:4]} •• ••• {value[-2:]}"


def _fernet() -> Fernet:
    key = hashlib.sha256(b"checky-contact-seal|" + _secret()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def unseal(token: str | None) -> str | None:
    if not token or not configured():
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def protect(contact: str) -> tuple[Kind, str, str, str]:
    """(kind, hash, masked, sealed) for a contact typed by the public; ValueError if unreadable."""
    kind, value = normalise(contact)
    return kind, digest(kind, value), mask(kind, value), seal(value)
