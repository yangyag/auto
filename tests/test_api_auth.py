import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import jwt

from app.api import auth


class MobileApiAuthTest(unittest.TestCase):
    def test_verify_password_uses_env_credentials(self):
        env = {
            "MOBILE_API_USERNAME": "operator",
            "MOBILE_API_PASSWORD": "secret-password",
        }
        with patch.dict("os.environ", env, clear=True):
            self.assertTrue(auth.verify_password("operator", "secret-password"))
            self.assertFalse(auth.verify_password("operator", "wrong"))
            self.assertFalse(auth.verify_password("other", "secret-password"))

    def test_verify_password_fails_when_password_unconfigured(self):
        with patch.dict("os.environ", {"MOBILE_API_USERNAME": "operator"}, clear=True):
            self.assertFalse(auth.verify_password("operator", ""))

    def test_create_and_decode_access_token(self):
        env = {
            "MOBILE_API_USERNAME": "operator",
            "MOBILE_API_PASSWORD": "secret-password",
            "MOBILE_API_JWT_SECRET": "jwt-test-secret-with-at-least-32-bytes",
        }
        with patch.dict("os.environ", env, clear=True):
            token = auth.create_access_token("operator")
            payload = auth.decode_access_token(token)

        self.assertEqual(payload["sub"], "operator")
        self.assertEqual(payload["typ"], "access")
        self.assertIn("jti", payload)

        now_ts = int(datetime.now(timezone.utc).timestamp())
        self.assertLessEqual(payload["iat"], now_ts + 1)
        self.assertGreater(payload["exp"], now_ts)
        self.assertLessEqual(payload["exp"] - payload["iat"], 15 * 60)

    def test_decode_access_token_rejects_wrong_type(self):
        jwt_secret = "jwt-test-secret-with-at-least-32-bytes"
        env = {"MOBILE_API_JWT_SECRET": jwt_secret}
        with patch.dict("os.environ", env, clear=True):
            token = jwt.encode(
                {"sub": "operator", "typ": "refresh"},
                jwt_secret,
                algorithm=auth.JWT_ALGORITHM,
            )
            with self.assertRaises(auth.AuthError):
                auth.decode_access_token(token)

    def test_create_refresh_token_returns_opaque_token_hash_and_expiry(self):
        with patch.dict("os.environ", {}, clear=True):
            token, token_hash, expires_at = auth.create_refresh_token()

        self.assertNotEqual(token, token_hash)
        self.assertEqual(token_hash, hashlib.sha256(token.encode("utf-8")).hexdigest())
        self.assertEqual(token_hash, auth.hash_refresh_token(token))
        self.assertGreater(expires_at, datetime.now(timezone.utc))

    def test_totp_disabled_when_secret_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(auth.totp_required())
            self.assertTrue(auth.verify_totp(None))
            self.assertTrue(auth.verify_totp("not-used"))
            auth.validate_command_totp(None)


if __name__ == "__main__":
    unittest.main()
