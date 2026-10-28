"""Authentication service and transparent upgrades for legacy password hashes."""
from accounting_app.config import PASSWORD_MIN_LENGTH, USERNAME_MIN_LENGTH
from accounting_app.database.connection import DBManager
from accounting_app.database.models import User


class AnonymousUser:
    """Read-only stand-in for an unauthenticated user."""
    username = None
    is_admin = False
    buttons = ""

    def __str__(self):
        return "AnonymousUser"


class AuthManager:
    """Validate credentials while resetting state before every authentication attempt."""

    def __init__(self):
        self.user = AnonymousUser()
        self.is_valid = False
        self.errors = []

    def validate(self, username, password):
        self.user = AnonymousUser()
        self.is_valid = False
        self.errors = []

        normalized_username = username.strip() if isinstance(username, str) else ""
        if len(normalized_username) < USERNAME_MIN_LENGTH:
            self.errors.append("نام کاربری باید حداقل ۴ نویسه داشته باشد.")
            return False
        if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
            self.errors.append("رمز عبور باید حداقل ۴ نویسه داشته باشد.")
            return False

        with DBManager():
            user = User.get_or_none(User.username == normalized_username)
            if user is None:
                self.errors.append("کاربری با این نام پیدا نشد.")
                return False
            if not user.check_password(password):
                self.errors.append("رمز عبور نادرست است.")
                return False
            if user.password_needs_upgrade():
                user.set_password(password)
                user.save(only=[User.password, User.updated_at])
            self.user = user
            self.is_valid = True
        return True

    def __call__(self):
        return self.user

    def is_authenticated(self):
        return self.is_valid
