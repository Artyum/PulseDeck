from app.services.uploads import sanitize_original_filename


class TestSanitizeOriginalFilename:
    def test_none(self):
        assert sanitize_original_filename(None) == "plik"

    def test_empty_string(self):
        assert sanitize_original_filename("") == "plik"

    def test_normal_filename(self):
        assert sanitize_original_filename("photo.jpg") == "photo.jpg"

    def test_strips_path_windows(self):
        assert sanitize_original_filename(r"C:\Users\test\photo.jpg") == "photo.jpg"

    def test_strips_path_unix(self):
        assert sanitize_original_filename("/home/user/photo.jpg") == "photo.jpg"

    def test_mixed_separators(self):
        assert sanitize_original_filename("folder\\subdir/file.txt") == "file.txt"

    def test_dot_is_placeholder(self):
        assert sanitize_original_filename(".") == "plik"

    def test_double_dot_is_placeholder(self):
        assert sanitize_original_filename("..") == "plik"

    def test_long_name_truncated(self):
        long_name = "a" * 300 + ".txt"
        result = sanitize_original_filename(long_name)
        assert len(result) == 255

    def test_whitespace_kept(self):
        assert sanitize_original_filename("my file.txt") == "my file.txt"
