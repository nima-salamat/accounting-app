"""Balanced ledger posting helpers for sales and later financial workflows."""
from decimal import Decimal

from accounting_app.database.connection import DBManager
from accounting_app.database.models import JournalEntry, JournalLine, LedgerAccount


DEFAULT_SALE_ACCOUNTS = (
    ("1000", "صندوق نقدی", "asset", "وجوه نقد و تسویه پرداخت"),
    ("1010", "بانک و تسویه کارت‌خوان", "asset", "وجوه بانکی و تسویه پرداخت"),
    ("1100", "حساب‌های دریافتنی", "asset", "مطالبات از مشتریان"),
    ("1200", "موجودی کالا", "asset", "حساب کنترل موجودی رهگیری‌شده"),
    ("2200", "اعتبار فروشگاه", "liability", "اعتبار قابل استفاده توسط مشتریان"),
    ("4000", "درآمد فروش", "income", "درآمد عملیاتی"),
    ("5000", "بهای تمام‌شده کالای فروش‌رفته", "expense", "بهای کالاهای دارای رهگیری موجودی"),
)


def _account(code, name, account_type, description):
    item, _created = LedgerAccount.get_or_create(
        code=code,
        defaults={
            "name": name,
            "account_type": account_type,
            "description": description,
            "is_active": True,
        },
    )
    return item


def post_sale_journal(receipt, user, items, total, paid, *, payment_method="cash", reference_id=None):
    """Post or refresh the balanced ledger entry for a receipt inside its transaction.

    Items are tuples: (product_id, buy_price, sell_price, quantity, product_name, tracked_stock).
    Inventory and COGS are posted only for products using stock tracking.
    """
    with DBManager():
        accounts = {
            code: _account(code, name, kind, description)
            for code, name, kind, description in DEFAULT_SALE_ACCOUNTS
        }
        revenue = Decimal(str(total)).quantize(Decimal("0.01"))
        cost_total = sum(
            (
                Decimal(str(buy_price)).quantize(Decimal("0.0001")) * int(quantity)
                for _product_id, buy_price, _sell_price, quantity, _name, tracked in items
                if tracked
            ),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        entry_reference = "SALE:{}".format(reference_id or receipt.id)
        entry = JournalEntry.get_or_none(JournalEntry.reference == entry_reference)
        entry_number = "SALE-{}".format(str(reference_id or receipt.id).replace("-", "").upper())
        debit_total = (revenue + cost_total).quantize(Decimal("0.01"))
        credit_total = debit_total
        if entry is None:
            entry = JournalEntry.create(
                entry_number=entry_number,
                entry_date=receipt.created_at.date(),
                description="فروش شمارهٔ روزانهٔ {}".format(receipt.day_receipt_id),
                reference=entry_reference,
                status="posted",
                created_by=user.id,
                created_by_name=user.username,
                debit_total=debit_total,
                credit_total=credit_total,
            )
        else:
            JournalLine.delete().where(JournalLine.entry == entry.id).execute()
            entry.entry_date = receipt.created_at.date()
            entry.description = "اصلاح فروش شمارهٔ روزانهٔ {}".format(receipt.day_receipt_id)
            entry.status = "posted"
            entry.created_by = user.id
            entry.created_by_name = user.username
            entry.debit_total = debit_total
            entry.credit_total = credit_total
            entry.is_year_closing = False
            entry.save(only=[
                JournalEntry.entry_date, JournalEntry.description, JournalEntry.status,
                JournalEntry.created_by, JournalEntry.created_by_name,
                JournalEntry.debit_total, JournalEntry.credit_total,
                JournalEntry.is_year_closing, JournalEntry.updated_at,
            ])

        if not paid:
            settlement_account = accounts["1100"]
            settlement_description = "مطالبهٔ فروش پرداخت‌نشده"
        elif payment_method == "card" or payment_method == "bank_transfer":
            settlement_account = accounts["1010"]
            settlement_description = "تسویهٔ بانکی / کارت‌خوان"
        elif payment_method == "store_credit":
            settlement_account = accounts["2200"]
            settlement_description = "استفاده از اعتبار فروشگاه"
        else:
            settlement_account = accounts["1000"]
            settlement_description = "دریافت نقدی فروش"
        JournalLine.create(
            entry=entry.id,
            account=settlement_account.id,
            description=settlement_description,
            debit=revenue,
            credit=Decimal("0"),
        )
        JournalLine.create(
            entry=entry.id,
            account=accounts["4000"].id,
            description="درآمد فروش",
            debit=Decimal("0"),
            credit=revenue,
        )
        if cost_total > 0:
            JournalLine.create(
                entry=entry.id,
                account=accounts["5000"].id,
                description="بهای تمام‌شدهٔ کالای رهگیری‌شده",
                debit=cost_total,
                credit=Decimal("0"),
            )
            JournalLine.create(
                entry=entry.id,
                account=accounts["1200"].id,
                description="کاهش موجودی کالای فروخته‌شده",
                debit=Decimal("0"),
                credit=cost_total,
            )
        return entry
