import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from broker.kis.auth import KisAuth
from broker.kis.token import KisToken


class KisAuthTest(unittest.TestCase):
    def setUp(self):
        KisAuth._shared_token = None
        KisAuth._shared_error = None
        KisAuth._retry_after = 0.0

    def tearDown(self):
        KisAuth._shared_token = None
        KisAuth._shared_error = None
        KisAuth._retry_after = 0.0

    def test_sessions_share_one_valid_token_in_process(self):
        token = KisToken(
            access_token="not-a-real-token",
            token_type="Bearer",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        first = KisAuth(object())
        second = KisAuth(object())

        with patch.object(KisAuth, "_authenticate", return_value=token) as issue:
            self.assertIs(token, first.get_token())
            self.assertIs(token, second.get_token())

        issue.assert_called_once()

    def test_authentication_failure_is_shared_during_cooldown(self):
        first = KisAuth(object())
        second = KisAuth(object())

        with patch.object(
            KisAuth,
            "_authenticate",
            side_effect=RuntimeError("limited"),
        ) as issue:
            with self.assertRaisesRegex(RuntimeError, "limited"):
                first.get_token()
            with self.assertRaisesRegex(RuntimeError, "limited"):
                second.get_token()

        issue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
