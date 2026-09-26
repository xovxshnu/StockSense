import hashlib
import logging

import pytest

from app.core import security


def legacy_hash(password: str) -> str:
    """The pre-versioning format: "<salt hex>$<digest hex>", fixed N=2**14, r=8, p=1."""
    salt = bytes(range(16))
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def test_new_hash_is_versioned_and_verifies() -> None:
    stored = security.hash_password("correct-horse")
    scheme, n, r, p, salt, digest = stored.split("$")
    assert (scheme, int(n), int(r), int(p)) == ("scrypt", 2**14, 8, 1)
    assert len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 32
    assert security.verify_password("correct-horse", stored)
    assert not security.verify_password("wrong-horse", stored)
    assert "correct-horse" not in stored


def test_hashes_are_salted() -> None:
    assert security.hash_password("same") != security.hash_password("same")


def test_legacy_format_hashes_still_verify() -> None:
    stored = legacy_hash("correct-horse")
    assert stored.count("$") == 1
    assert security.verify_password("correct-horse", stored)
    assert not security.verify_password("wrong-horse", stored)


def test_raising_the_cost_does_not_invalidate_existing_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    old = security.hash_password("correct-horse")
    monkeypatch.setattr(security, "SCRYPT_N", 2**15)
    monkeypatch.setattr(security, "SCRYPT_R", 8)
    new = security.hash_password("correct-horse")
    assert new.split("$")[1] == str(2**15) and old.split("$")[1] == str(2**14)
    # both verify, each with the parameters stored in its own hash
    assert security.verify_password("correct-horse", old)
    assert security.verify_password("correct-horse", new)
    assert not security.verify_password("wrong-horse", new)


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "garbage",
        "$",
        "a$b$c",
        "scrypt$16384$8$1$zz$zz",  # not hex
        "scrypt$16384$8$1$00$",  # empty digest
        "scrypt$16384$8$1$$00",  # empty salt
        "scrypt$abc$8$1$00$00",  # non-numeric parameter
        "scrypt$16384$8$1$00",  # too few fields
        "scrypt$16384$8$1$00$00$00",  # too many fields
        "bcrypt$16384$8$1$00$00",  # unknown scheme
        "scrypt$16385$8$1$00$00",  # N not a power of two
        "scrypt$0$8$1$00$00",
        "scrypt$16384$0$1$00$00",
        "scrypt$16384$8$0$00$00",
        "scrypt$-16384$8$1$00$00",
        f"scrypt${2**40}$8$1$00$00",  # absurd cost: rejected before any work
        "scrypt$16384$1000000$1$00$00",
        "00$",
        "$00",
    ],
)
def test_malformed_hashes_fail_safely(malformed: str) -> None:
    assert security.verify_password("anything", malformed) is False


def test_verification_errors_do_not_leak_password_material(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        assert security.verify_password("s3cret-password", "scrypt$abc$8$1$00$00") is False
    assert "s3cret-password" not in caplog.text
