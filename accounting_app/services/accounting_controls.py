"""Fiscal-period write guards shared by sales, returns and the general ledger."""
from accounting_app.database.models import FiscalYear


class FiscalPeriodClosedError(ValueError):
    """Raised when a transaction targets a closed accounting period."""


def ensure_period_open(entry_date, actor=None, action="entry"):
    """Disallow backdated or current-period postings inside explicitly closed fiscal years."""
    fiscal_year = (
        FiscalYear.select()
        .where((FiscalYear.start_date <= entry_date) & (FiscalYear.end_date >= entry_date))
        .first()
    )
    if fiscal_year is not None and fiscal_year.status == "closed":
        raise FiscalPeriodClosedError(
            "سال مالی «{}» از {} تا {} بسته است؛ برای ثبت {} باید مدیر/حسابدار ابتدا سال مالی را با ثبت دلیل بازگشایی کند.".format(
                fiscal_year.name,
                fiscal_year.start_date.isoformat(),
                fiscal_year.end_date.isoformat(),
                action,
            )
        )
    return fiscal_year
