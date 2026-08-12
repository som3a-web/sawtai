from datetime import timedelta

import pytest
from fastapi import HTTPException

from sawtai.auth.service import (
    UserContext,
    _encode_token,
    decode_token,
    has_permission,
    hash_password,
    require,
    verify_password,
)
from sawtai.config import Settings


def user(*permissions: str) -> UserContext:
    return UserContext(
        user_id="00000000-0000-0000-0000-000000000201",
        tenant_id="00000000-0000-0000-0000-000000000001",
        email="officer@sawtai.ae",
        display_name_ar="مريم الكتبي",
        display_name_en="Maryam Al Ketbi",
        org_unit_id="00000000-0000-0000-0000-000000000101",
        roles=("comms_officer",),
        permissions=frozenset(permissions),
        mfa_enrolled=True,
    )


def test_passwords_use_argon2_and_reject_mismatch() -> None:
    encoded = hash_password("SawtAI-2026!")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "SawtAI-2026!")
    assert not verify_password(encoded, "incorrect-password")


def test_access_token_is_signed_and_type_checked() -> None:
    settings = Settings(JWT_SECRET="unit-test-secret")
    token, _, _ = _encode_token(
        user_id="00000000-0000-0000-0000-000000000201",
        tenant_id="00000000-0000-0000-0000-000000000001",
        token_type="access",
        lifetime=timedelta(minutes=5),
        settings=settings,
    )
    assert decode_token(token, expected_type="access", settings=settings)["type"] == "access"
    with pytest.raises(HTTPException):
        decode_token(token, expected_type="refresh", settings=settings)


@pytest.mark.asyncio
async def test_permission_dependency_supports_exact_and_scoped_wildcards() -> None:
    officer = user("analytics:read")
    assert has_permission(officer, "analytics:read")
    assert await require("analytics:read")(user=officer) == officer

    administrator = user("user:*")
    assert has_permission(administrator, "user:create")
    with pytest.raises(HTTPException) as error:
        await require("message:read")(user=administrator)
    assert error.value.status_code == 403
