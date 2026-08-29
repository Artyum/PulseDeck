import pytest

from app.utils.password import (
    hash_password,
    validate_password_strength,
    verify_password,
)


class TestValidatePasswordStrength:
    def test_valid_password(self):
        assert validate_password_strength("Admin123!abcd") == "Admin123!abcd"

    def test_too_short(self):
        with pytest.raises(ValueError, match=r".*at least.*"):
            validate_password_strength("Ab1!")

    def test_no_lowercase(self):
        with pytest.raises(ValueError, match=".*lower.*"):
            validate_password_strength("ADMIN123!XXXX")

    def test_no_uppercase(self):
        with pytest.raises(ValueError, match=".*upper.*"):
            validate_password_strength("admin123!xxxx")

    def test_no_digit(self):
        with pytest.raises(ValueError, match=".*digit.*"):
            validate_password_strength("Admin!!!!!!!!")

    def test_no_special(self):
        with pytest.raises(ValueError, match=".*special.*"):
            validate_password_strength("Admin1234xxxx")

    def test_too_long_bytes(self):
        # 73-byte password (72 is max)
        long_pwd = "A" * 8 + "a" * 8 + "1!" + "x" * 100  # will be > 72 bytes
        with pytest.raises(ValueError, match=".*too long.*"):
            validate_password_strength(long_pwd)

    def test_exactly_min_length_with_requirements(self):
        assert validate_password_strength("Abcd12!x9yzW") == "Abcd12!x9yzW"

    def test_unicode_characters(self):
        assert validate_password_strength("Hasło123!abcd") == "Hasło123!abcd"


class TestHashVerify:
    def test_roundtrip(self):
        h = hash_password("Test1234!abcd")
        assert verify_password("Test1234!abcd", h)

    def test_wrong_password(self):
        h = hash_password("Test1234!abcd")
        assert not verify_password("wrong", h)

    def test_long_password_fails_gracefully(self):
        long_pwd = "A" * 73
        assert verify_password(long_pwd, "some_hash") is False

    def test_invalid_hash(self):
        assert verify_password("Test1234!abcd", "invalid_hash") is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("Test1234!abcd")
        h2 = hash_password("Test1234!abcd")
        assert h1 != h2
