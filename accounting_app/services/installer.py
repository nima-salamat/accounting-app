"""First-run installation workflow and initial administrator provisioning."""
from accounting_app.config import PASSWORD_MIN_LENGTH, USERNAME_MIN_LENGTH
from accounting_app.database.connection import DBManager
from accounting_app.database.extension_models import AppSetting
from accounting_app.services.business_profiles import profile_metadata
from accounting_app.database.models import User
from accounting_app.services.schema_registry import register_schema_rows
from accounting_app.services.validation import validate_password, validate_username

SETUP_COMPLETE_KEY = "initial_setup_complete"


def is_setup_required():
    """Show setup when the database has no users, including after administrator loss."""
    with DBManager():
        setting = AppSetting.get_or_none(AppSetting.key == SETUP_COMPLETE_KEY)
        if User.select().exists():
            # Existing installations predate the setup marker and must remain usable.
            if setting is None:
                AppSetting.create(key=SETUP_COMPLETE_KEY, value="1")
            elif setting.value != "1":
                setting.value = "1"
                setting.save(only=[AppSetting.value, AppSetting.updated_at])
            return False
        return True

def complete_initial_setup(username, password, password_confirmation, schema_rows=None, company_name="کسب‌وکار من", business_profile="general", product_buy_price_required=None):
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
        if User.select().exists():
            raise ValueError("پایگاه داده از قبل کاربر دارد؛ نصب اولیهٔ دیگری مجاز نیست.")
        if User.get_or_none(User.username == normalized_username) is not None:
            raise ValueError("این نام کاربری قبلاً ثبت شده است.")

        user = User(username=normalized_username, password="", is_admin=True)
        user.set_password(validated_password)
        user.save(force_insert=True)
        register_schema_rows(schema_rows or [], allow_existing=True)
        profile = profile_metadata(business_profile, company_name, product_buy_price_required)
        company_setting = AppSetting.get_or_none(AppSetting.key == "company_profile")
        serialized_profile = __import__("json").dumps(profile, ensure_ascii=False, separators=(",", ":"))
        if company_setting is None:
            AppSetting.create(key="company_profile", value=serialized_profile)
        else:
            company_setting.value = serialized_profile
            company_setting.save(only=[AppSetting.value, AppSetting.updated_at])
        invoice_setting = AppSetting.get_or_none(AppSetting.key == "invoice_template")
        if invoice_setting is None:
            invoice_template = {
                "company_name": profile["company_name"],
                "legal_id": "",
                "address": "",
                "phone": "",
                "footer": "از خرید شما سپاسگزاریم.",
                "paper_size": "A4",
                "accent_color": "#3157A4",
            }
            AppSetting.create(
                key="invoice_template",
                value=__import__("json").dumps(invoice_template, ensure_ascii=False, separators=(",", ":")),
            )
        if setting is None:
            AppSetting.create(key=SETUP_COMPLETE_KEY, value="1")
        else:
            setting.value = "1"
            setting.save(only=[AppSetting.value, AppSetting.updated_at])
        return user
