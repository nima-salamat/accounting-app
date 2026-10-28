import binascii
import hashlib
import tempfile
import unittest
from pathlib import Path

from peewee import DoesNotExist

from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.models import User
from accounting_app.database.schema import create_tables
from accounting_app.services.authentication import AuthManager


class DatabaseAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        initialize_db(Path(self.temp_dir.name) / "test.db")
        with DBManager() as database:
            create_tables(database)
            User.delete().execute()
            user = User(username="alice", password="")
            user.set_password("correct horse")
            user.save(force_insert=True)

    def tearDown(self):
        if not db.is_closed():
            db.close()
        self.temp_dir.cleanup()

    def test_password_hash_is_salted_and_verifiable(self):
        with DBManager():
            user = User.get(User.username == "alice")
            first_hash = user.password
            self.assertTrue(user.check_password("correct horse"))
            self.assertFalse(user.check_password("wrong password"))
            user.set_password("correct horse")
            self.assertNotEqual(first_hash, user.password)

    def test_legacy_sha256_hash_is_verified_and_upgraded(self):
        legacy_password = "old password"
        with DBManager():
            user = User.get(User.username == "alice")
            user.password = hashlib.sha256(legacy_password.encode("utf-8")).hexdigest()
            user.save(only=[User.password, User.updated_at])
        manager = AuthManager()
        self.assertTrue(manager.validate("alice", legacy_password))
        self.assertTrue(manager.user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(manager.user.check_password(legacy_password))

    def test_legacy_pbkdf2_hash_is_verified_and_upgraded(self):
        legacy_password = "historic password"
        salt = bytes(range(16))
        digest = hashlib.pbkdf2_hmac("sha256", legacy_password.encode("utf-8"), salt, 100_000)
        stored_legacy_hash = binascii.hexlify(salt + digest).decode("ascii")
        with DBManager():
            user = User.get(User.username == "alice")
            user.password = stored_legacy_hash
            user.save(only=[User.password, User.updated_at])
        manager = AuthManager()
        self.assertTrue(manager.validate("alice", legacy_password))
        self.assertTrue(manager.user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(manager.user.check_password(legacy_password))

    def test_authentication_state_resets_after_failed_attempt(self):
        manager = AuthManager()
        self.assertTrue(manager.validate("alice", "correct horse"))
        self.assertFalse(manager.validate("alice", "wrong password"))
        self.assertFalse(manager.is_authenticated())
        self.assertIsNone(manager.user.username)
        self.assertEqual(len(manager.errors), 1)

    def test_failed_transaction_rolls_back(self):
        with self.assertRaises(RuntimeError):
            with DBManager():
                User.create(username="rollback", password="unused")
                raise RuntimeError("force rollback")
        with DBManager():
            with self.assertRaises(DoesNotExist):
                User.get(User.username == "rollback")


if __name__ == "__main__":
    unittest.main()
