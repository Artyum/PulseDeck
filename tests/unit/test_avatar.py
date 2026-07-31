from app.utils.avatar import avatar_tone, user_initials


class TestUserInitials:
    def test_none(self):
        assert user_initials(None) == "?"

    def test_empty(self):
        assert user_initials("") == "?"

    def test_whitespace(self):
        assert user_initials("   ") == "?"

    def test_single_name(self):
        assert user_initials("Ada") == "A"

    def test_two_names(self):
        assert user_initials("Ada Lovelace") == "AL"

    def test_three_names_uses_first_and_last(self):
        assert user_initials("Ada Augusta Lovelace") == "AL"

    def test_lowercase(self):
        assert user_initials("jan kowalski") == "JK"


class TestAvatarTone:
    def test_modulo(self):
        assert avatar_tone(0) == 0
        assert avatar_tone(31) == 31
        assert avatar_tone(32) == 0
        assert avatar_tone(33) == 1
