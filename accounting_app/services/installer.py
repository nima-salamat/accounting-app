"""First-run installation workflow and initial administrator provisioning."""
from accounting_app.config import PASSWORD_MIN_LENGTH, USERNAME_MIN_LENGTH
from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import AppSetting
from accounting_app.database.models import User
from accounting_app.services.schema_registry import register_schema_rows
from accounting_app.services.validation import validate_password, validate_username

SETUP_COMPLETE_KEY = "initial_setup_complete"


def is_setup_required():
    """Show the installer only for a database that has not been initialized."""
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == SETUP_COMPLETE_KEY)
        if setting is not None and setting.value == "1":
            return False
        if User.select().exists():
            # Existing installations predate the setup marker and must remain usable.
            if setting is None:
                AppSetting.create(key=SETUP_COMPLETE_KEY, value="1")
            else:
                setting.value = "1"
                setting.save(only=[AppSetting.value, AppSetting.updated_at])
            return False
        return True


def complete_initial_setup(username, password, password_confirmation, schema_rows=None):
    """Create the first admin and schema metadata as one atomic operation."""
    normalized_username = validate_username(username)
    if len(normalized_username) < USERNAME_MIN_LENGTH:
        raise ValueError("نام کاربری باید حداقل ۴ نویسه داشته باشد.")
    validated_password = validate_password(password)
    if len(validated_password) < PASSWORD_MIN_LENGTH:
        raise ValueError("رمز عبور باید حداقل ۴ نویسه داشته باشد.")
    if validated_password != password_confirmation:
        raise ValueError("تکرار رمز عبور با رمز عبور یکسان نیست.")

    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == SETUP_COMPLETE_KEY)
        if (setting is not None and setting.value == "1") or User.select().exists():
            raise ValueError("نصب اولیه قبلاً انجام شده است؛ مدیر دیگری از این مسیر ساخته نمی‌شود.")
        if User.get_or_none(User.username == normalized_username) is not None:
            raise ValueError("این نام کاربری قبلاً ثبت شده است.")

        user = User(username=normalized_username, password="", is_admin=True)
        user.set_password(validated_password)
        user.save(force_insert=True)
        register_schema_rows(schema_rows or [])
        if setting is None:
            AppSetting.create(key=SETUP_COMPLETE_KEY, value="1")
        else:
            setting.value = "1"
            setting.save(only=[AppSetting.value, AppSetting.updated_at])
        return user
