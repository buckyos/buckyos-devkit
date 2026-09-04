import io
import unittest

from src.console import _configure_output_stream


class ConsoleOutputTests(unittest.TestCase):
    def test_unsupported_characters_are_replaced_for_legacy_code_page(self):
        output = io.BytesIO()
        stream = io.TextIOWrapper(output, encoding="cp1252")

        _configure_output_stream(stream)
        stream.write("🔄 Reinstalling")
        stream.flush()

        self.assertEqual(output.getvalue(), b"? Reinstalling")
        stream.detach()

    def test_utf8_output_is_preserved(self):
        output = io.BytesIO()
        stream = io.TextIOWrapper(output, encoding="utf-8")

        _configure_output_stream(stream)
        stream.write("🔄 Reinstalling")
        stream.flush()

        self.assertEqual(output.getvalue().decode("utf-8"), "🔄 Reinstalling")
        stream.detach()


if __name__ == "__main__":
    unittest.main()
