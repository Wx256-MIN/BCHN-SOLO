import unittest

from cashaddr import is_valid_cashaddr


class CashAddrValidationTests(unittest.TestCase):
    def test_accepts_known_valid_mainnet_address(self):
        self.assertTrue(is_valid_cashaddr("bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"))

    def test_rejects_checksum_typo(self):
        self.assertFalse(is_valid_cashaddr("bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6q"))

    def test_rejects_wrong_prefix(self):
        self.assertFalse(is_valid_cashaddr("bchtest:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"))

    def test_rejects_mixed_case(self):
        self.assertFalse(is_valid_cashaddr("bitcoincash:Qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"))

    def test_rejects_invalid_alphabet(self):
        self.assertFalse(is_valid_cashaddr("bitcoincash:q" + "i" * 41))

    def test_rejects_short_or_non_string_input(self):
        self.assertFalse(is_valid_cashaddr("bitcoincash:q123"))
        self.assertFalse(is_valid_cashaddr(None))


if __name__ == "__main__":
    unittest.main()
