import hashlib
import hmac


def verify_meta_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    if not signature or not app_secret:
        return False
    algorithm, separator, received = signature.partition("=")
    if not separator or algorithm != "sha256" or len(received) != 64:
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)
