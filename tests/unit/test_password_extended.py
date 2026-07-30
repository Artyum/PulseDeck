import pytest

from app.utils.password import (
    validate_password_strength,
    hash_password,
    verify_password,
)


class TestValidatePasswordStrength:
    def test_valid_password(self):
        assert validate_password_strength("Admin123!") == "Admin123!"

    def test_too_short(self):
        with pytest.raises(ValueError, match=r".*at least.*"):
            validate_password_strength("Ab1!")

    def test_no_lowercase(self):
        with pytest.raises(ValueError, match=".*lower.*"):
            validate_password_strength("ADMIN123!")

    def test_no_uppercase(self):
        with pytest.raises(ValueError, match=".*upper.*"):
            validate_password_strength("admin123!")

    def test_no_digit(self):
        with pytest.raises(ValueError, match=".*digit.*"):
            validate_password_strength("Admin!!!X")

    def test_no_special(self):
        with pytest.raises(ValueError, match=".*special.*"):
            validate_password_strength("Admin1234")

    def test_too_long_bytes(self):
        # 73-byte password (72 is max)
        long_pwd = "A" * 8 + "a" * 8 + "1!" + "x" * 100  # will be > 72 bytes
        with pytest.raises(ValueError, match=".*too long.*"):
            validate_password_strength(long_pwd)

    def test_exactly_min_length_with_requirements(self):
        # 8 chars, all requirements met
        assert validate_password_strength("Abcd1!x9") == "Abcd1!x9"

    def test_unicode_characters(self):
        # Unicode password with all requirements
        assert validate_password_strength("Hasło123!") == "Hasło123!"


class TestHashVerify:
    def test_roundtrip(self):
        h = hash_password("Test1234!")
        assert verify_password("Test1234!", h)

    def test_wrong_password(self):
        h = hash_password("Test1234!")
        assert not verify_password("wrong", h)

    def test_long_password_fails_gracefully(self):
        long_pwd = "A" * 73
        assert verify_password(long_pwd, "some_hash") is False

    def test_invalid_hash(self):
        assert verify_password("Test1234!", "invalid_hash") is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("Test1234!")
        h2 = hash_password("Test1234!")
        assert h1 != h2  # bcrypt salts differently
