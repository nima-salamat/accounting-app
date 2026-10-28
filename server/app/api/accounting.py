"""Fiscal periods, chart of accounts, balanced journal entries and accounting reports."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from peewee import fn

from accounting_app.database.connection import DBManager
from accounting_app.database.models import (
    AuditEvent, FiscalYear, JournalEntry, JournalLine, LedgerAccount, Receipt,
    SaleReturn, StockMovement,
)
from accounting_app.services.accounting_controls import ensure_period_open
from accounting_app.services.audit import record_audit
from server.app.permissions import require_permission
from server.app.schemas import (
    FiscalYearCreate, FiscalYearReopen, JournalEntryCreate, LedgerAccountCreate,
)

router = APIRouter(tags=["general ledger and fiscal periods"])

DEFAULT_ACCOUNTS = (
    ("1000", "صندوق نقدی", "asset", "وجوه نقد"),
    ("1010", "بانک", "asset", "حساب‌های بانکی"),
    ("1100", "حساب‌های دریافتنی", "asset", "مطالبات از مشتریان"),
    ("1200", "موجودی کالا", "asset", "حساب کنترل موجودی"),
    ("2000", "حساب‌های پرداختنی", "liability", "بدهی به تأمین‌کنندگان"),
    ("2100", "مالیات پرداختنی", "liability", "مالیات و عوارض"),
    ("2200", "اعتبار فروشگاه", "liability", "اعتبار قابل استفاده توسط مشتریان"),
    ("3000", "سرمایه", "equity", "سرمایه مالک"),
    ("3100", "سود و زیان انباشته", "equity", "سود/زیان دوره‌های قبل"),
    ("4000", "درآمد فروش", "income", "درآمد عملیاتی"),
    ("4100", "برگشت از فروش", "income", "حساب کاهنده درآمد فروش"),
    ("5000", "بهای تمام‌شده کالای فروش‌رفته", "expense", "بهای کالای فروخته‌شده"),
    ("6000", "هزینه‌های عملیاتی", "expense", "هزینه‌های جاری"),
)


def _seed_chart():
    if LedgerAccount.select().exists():
        return
    for code, name, kind, description in DEFAULT_ACCOUNTS:
        LedgerAccount.create(code=code, name=name, account_type=kind, description=description)


def _fiscal_payload(year):
    return {
        "id": str(year.id),
        "name": year.name,
        "start_date": year.start_date.isoformat(),
        "end_date": year.end_date.isoformat(),
        "status": year.status,
        "opened_by_name": year.opened_by_name,
        "closed_by_name": year.closed_by_name,
        "closed_at": year.closed_at.isoformat() if year.closed_at else None,
        "reopen_reason": year.reopen_reason,
        "created_at": year.created_at.isoformat(),
    }


def _account_payload(account):
    return {
        "id": str(account.id),
        "code": account.code,
        "name": account.name,
        "account_type": account.account_type,
        "is_active": bool(account.is_active),
        "description": account.description,
    }


def _entry_payload(entry, include_lines=True):
    result = {
        "id": str(entry.id),
        "entry_number": entry.entry_number,
        "entry_date": entry.entry_date.isoformat(),
        "description": entry.description,
        "reference": entry.reference,
        "status": entry.status,
        "created_by_name": entry.created_by_name,
        "debit_total": str(entry.debit_total),
        "credit_total": str(entry.credit_total),
        "is_year_closing": bool(entry.is_year_closing),
        "created_at": entry.created_at.isoformat(),
    }
    if include_lines:
        result["lines"] = [
            {
                "id": str(line.id),
                "account_id": str(line.account_id),
                "account_code": line.account.code,
                "account_name": line.account.name,
                "description": line.description,
                "debit": str(line.debit),
                "credit": str(line.credit),
            }
            for line in JournalLine.select().where(JournalLine.entry == entry.id).order_by(JournalLine.created_at)
        ]
    return result


@router.get("/fiscal-years")
def list_fiscal_years(user=Depends(require_permission("fiscal_years", "read"))):
    with DBManager():
        return [
            _fiscal_payload(item)
            for item in FiscalYear.select().order_by(FiscalYear.start_date.desc())
        ]


@router.post("/fiscal-years", status_code=status.HTTP_201_CREATED)
def create_fiscal_year(payload: FiscalYearCreate, user=Depends(require_permission("fiscal_years", "create"))):
    with DBManager():
        overlap = FiscalYear.select().where(
            (FiscalYear.start_date <= payload.end_date)
            & (FiscalYear.end_date >= payload.start_date)
        ).exists()
        if overlap:
            raise HTTPException(status_code=409, detail="بازهٔ این سال مالی با سال مالی دیگری تداخل دارد.")
        year = FiscalYear.create(
            name=payload.name.strip(),
            start_date=payload.start_date,
            end_date=payload.end_date,
            status="open",
            opened_by_name=user.username,
        )
        record_audit(
            user, "fiscal_year.created", "fiscal_years", year.id,
            {"name": year.name, "start_date": year.start_date, "end_date": year.end_date},
        )
        return _fiscal_payload(year)


def _create_fiscal_closing_journal(year, user):
    """Close revenue/expense balances into retained earnings with a balanced entry."""
    _seed_chart()
    accounts = list(LedgerAccount.select().where(
        LedgerAccount.is_active == True,
        LedgerAccount.account_type.in_(("income", "expense")),
    ).order_by(LedgerAccount.code))
    closing_lines = []
    debit_total = Decimal("0")
    credit_total = Decimal("0")
    for account in accounts:
        totals = (
            JournalLine.select(
                fn.COALESCE(fn.SUM(JournalLine.debit), 0).alias("debit"),
                fn.COALESCE(fn.SUM(JournalLine.credit), 0).alias("credit"),
            )
            .join(JournalEntry)
            .where(
                (JournalLine.account == account.id)
                & (JournalEntry.entry_date >= year.start_date)
                & (JournalEntry.entry_date <= year.end_date)
                & (JournalEntry.status == "posted")
                & (JournalEntry.is_year_closing == False)
            )
            .dicts()
            .get()
        )
        debit = Decimal(str((totals or {}).get("debit") or 0)).quantize(Decimal("0.01"))
        credit = Decimal(str((totals or {}).get("credit") or 0)).quantize(Decimal("0.01"))
        balance = credit - debit if account.account_type == "income" else debit - credit
        if balance == 0:
            continue
        if account.account_type == "income":
            line_debit, line_credit = (balance, Decimal("0")) if balance > 0 else (Decimal("0"), -balance)
        else:
            line_debit, line_credit = (Decimal("0"), balance) if balance > 0 else (-balance, Decimal("0"))
        closing_lines.append({
            "account": account,
            "debit": line_debit,
            "credit": line_credit,
        })
        debit_total += line_debit
        credit_total += line_credit

    if not closing_lines:
        return None
    retained = LedgerAccount.get_or_none(LedgerAccount.code == "3100")
    if retained is None:
        retained = LedgerAccount.create(
            code="3100", name="سود و زیان انباشته",
            account_type="equity", description="سود/زیان دوره‌های قبل",
        )
    difference = debit_total - credit_total
    if difference > 0:
        closing_lines.append({"account": retained, "debit": Decimal("0"), "credit": difference})
        credit_total += difference
    elif difference < 0:
        closing_lines.append({"account": retained, "debit": -difference, "credit": Decimal("0")})
        debit_total += -difference
    if debit_total != credit_total:
        raise HTTPException(status_code=409, detail="سند بستن سال مالی متوازن نشد.")

    close_reference = "FISCAL-CLOSE:{}".format(year.id)
    entry = JournalEntry.get_or_none(JournalEntry.reference == close_reference)
    if entry is None:
        entry = JournalEntry.create(
            entry_number="CLOSE-{}".format(str(year.id).replace("-", "")[:16].upper()),
            entry_date=year.end_date,
            description="سند بستن درآمد و هزینهٔ سال مالی {}".format(year.name),
            reference=close_reference,
            status="posted",
            created_by=user.id,
            created_by_name=user.username,
            debit_total=debit_total,
            credit_total=credit_total,
            is_year_closing=True,
        )
    else:
        JournalLine.delete().where(JournalLine.entry == entry.id).execute()
        entry.entry_date = year.end_date
        entry.description = "سند بستن درآمد و هزینهٔ سال مالی {}".format(year.name)
        entry.status = "posted"
        entry.created_by = user.id
        entry.created_by_name = user.username
        entry.debit_total = debit_total
        entry.credit_total = credit_total
        entry.is_year_closing = True
        entry.save(only=[
            JournalEntry.entry_date, JournalEntry.description, JournalEntry.status,
            JournalEntry.created_by, JournalEntry.created_by_name,
            JournalEntry.debit_total, JournalEntry.credit_total,
            JournalEntry.is_year_closing, JournalEntry.updated_at,
        ])
    for line in closing_lines:
        JournalLine.create(
            entry=entry.id,
            account=line["account"].id,
            description="بستن سال مالی {}".format(year.name),
            debit=line["debit"],
            credit=line["credit"],
        )
    return entry


@router.post("/fiscal-years/{year_id}/close")
def close_fiscal_year(year_id: UUID, user=Depends(require_permission("fiscal_years", "update"))):
    with DBManager():
        year = FiscalYear.get_or_none(FiscalYear.id == year_id)
        if year is None:
            raise HTTPException(status_code=404, detail="سال مالی پیدا نشد.")
        if year.status == "closed":
            raise HTTPException(status_code=409, detail="این سال مالی از قبل بسته شده است.")
        journal_query = JournalEntry.select().where(
            (JournalEntry.entry_date >= year.start_date)
            & (JournalEntry.entry_date <= year.end_date)
            & (JournalEntry.status == "posted")
        )
        unbalanced = [
            entry.entry_number for entry in journal_query
            if Decimal(str(entry.debit_total)) != Decimal(str(entry.credit_total))
        ]
        if unbalanced:
            raise HTTPException(status_code=409, detail="اسناد نامتوازن وجود دارد؛ سال مالی بسته نشد.")
        if journal_query.where(JournalEntry.is_year_closing == True).exists():
            raise HTTPException(status_code=409, detail="این سال مالی قبلاً سند بستن دارد؛ برای رفع تعارض، از پنل حسابداری بررسی کنید.")
        closing_entry = _create_fiscal_closing_journal(year, user)
        receipts = Receipt.select().where(
            (Receipt.created_at >= datetime.combine(year.start_date, datetime.min.time()))
            & (Receipt.created_at <= datetime.combine(year.end_date, datetime.max.time()))
        )
        unpaid_count = receipts.where(Receipt.payed == False).count()
        sales_count = receipts.count()
        year.status = "closed"
        year.closed_by_name = user.username
        year.closed_at = datetime.now()
        year.save(only=[
            FiscalYear.status, FiscalYear.closed_by_name, FiscalYear.closed_at,
            FiscalYear.updated_at,
        ])
        record_audit(
            user, "fiscal_year.closed", "fiscal_years", year.id,
            {
                "name": year.name, "unpaid_receipts": unpaid_count, "receipt_count": sales_count,
                "closing_entry_id": str(closing_entry.id) if closing_entry else None,
                "closing_entry_number": closing_entry.entry_number if closing_entry else None,
            },
        )
        return {
            "year": _fiscal_payload(year),
            "closing_entry": _entry_payload(closing_entry) if closing_entry else None,
            "checklist": {
                "posted_journals_balanced": True,
                "receipt_count": sales_count,
                "unpaid_receipts": unpaid_count,
                "warning": "رسیدهای پرداخت‌نشده را پیش از بستن نهایی بررسی کنید." if unpaid_count else None,
            },
        }


@router.post("/fiscal-years/{year_id}/reopen")
def reopen_fiscal_year(
    year_id: UUID, payload: FiscalYearReopen,
    user=Depends(require_permission("fiscal_years", "update")),
):
    with DBManager():
        year = FiscalYear.get_or_none(FiscalYear.id == year_id)
        if year is None:
            raise HTTPException(status_code=404, detail="سال مالی پیدا نشد.")
        if year.status != "closed":
            raise HTTPException(status_code=409, detail="این سال مالی بسته نیست.")
        old_status = year.status
        closing_entry = JournalEntry.get_or_none(
            JournalEntry.reference == "FISCAL-CLOSE:{}".format(year.id)
        )
        if closing_entry is not None and closing_entry.status == "posted":
            closing_entry.status = "reversed"
            closing_entry.description = "معکوس‌شده — " + closing_entry.description
            closing_entry.save(only=[
                JournalEntry.status, JournalEntry.description, JournalEntry.updated_at,
            ])
        year.status = "open"
        year.reopen_reason = payload.reason.strip()
        year.closed_by_name = None
        year.closed_at = None
        year.save(only=[
            FiscalYear.status, FiscalYear.reopen_reason, FiscalYear.closed_by_name,
            FiscalYear.closed_at, FiscalYear.updated_at,
        ])
        record_audit(
            user, "fiscal_year.reopened", "fiscal_years", year.id,
            {
                "name": year.name,
                "previous_status": old_status,
                "reason": payload.reason.strip(),
                "reversed_closing_entry_id": str(closing_entry.id) if closing_entry else None,
            },
        )
        return _fiscal_payload(year)


@router.get("/accounts")
def list_accounts(user=Depends(require_permission("journals", "read"))):
    with DBManager():
        _seed_chart()
        return [
            _account_payload(item)
            for item in LedgerAccount.select().order_by(LedgerAccount.code)
        ]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(payload: LedgerAccountCreate, user=Depends(require_permission("journals", "create"))):
    with DBManager():
        if LedgerAccount.get_or_none(LedgerAccount.code == payload.code) is not None:
            raise HTTPException(status_code=409, detail="این کد حساب قبلاً ثبت شده است.")
        item = LedgerAccount.create(
            code=payload.code.strip(), name=payload.name.strip(),
            account_type=payload.account_type, description=payload.description,
        )
        record_audit(user, "ledger_account.created", "journals", item.id, _account_payload(item))
        return _account_payload(item)


@router.get("/journals")
def list_journals(
    response: Response,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    user=Depends(require_permission("journals", "read")),
):
    with DBManager():
        query = JournalEntry.select()
        if q and q.strip():
            term = q.strip()
            query = query.where(
                JournalEntry.entry_number.contains(term)
                | JournalEntry.description.contains(term)
                | JournalEntry.reference.contains(term)
            )
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [
            _entry_payload(item, include_lines=False)
            for item in query.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc()).paginate(page, page_size)
        ]


@router.get("/journals/{entry_id}")
def get_journal(entry_id: UUID, user=Depends(require_permission("journals", "read"))):
    with DBManager():
        entry = JournalEntry.get_or_none(JournalEntry.id == entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="سند حسابداری پیدا نشد.")
        return _entry_payload(entry)


@router.post("/journals", status_code=status.HTTP_201_CREATED)
def create_journal(payload: JournalEntryCreate, user=Depends(require_permission("journals", "create"))):
    try:
        with DBManager():
            ensure_period_open(payload.entry_date, actor=user, action="سند حسابداری")
            account_ids = {line.account_id for line in payload.lines}
            accounts = {
                item.id: item for item in LedgerAccount.select().where(LedgerAccount.id.in_(account_ids))
            }
            if len(accounts) != len(account_ids):
                raise HTTPException(status_code=422, detail="یک یا چند حساب انتخاب‌شده وجود ندارد.")
            if any(not account.is_active for account in accounts.values()):
                raise HTTPException(status_code=409, detail="یکی از حساب‌های انتخاب‌شده غیرفعال است.")
            debit = sum((line.debit for line in payload.lines), Decimal("0")).quantize(Decimal("0.01"))
            credit = sum((line.credit for line in payload.lines), Decimal("0")).quantize(Decimal("0.01"))
            if debit != credit or debit <= 0:
                raise HTTPException(status_code=422, detail="سند حسابداری باید متوازن باشد.")
            entry_number = "JE-{}-{}".format(payload.entry_date.strftime("%Y%m%d"), uuid4().hex[:8].upper())
            entry = JournalEntry.create(
                entry_number=entry_number,
                entry_date=payload.entry_date,
                description=payload.description.strip(),
                reference=payload.reference.strip() if payload.reference else None,
                status="posted",
                created_by=user.id,
                created_by_name=user.username,
                debit_total=debit,
                credit_total=credit,
            )
            for line in payload.lines:
                JournalLine.create(
                    entry=entry.id,
                    account=line.account_id,
                    description=line.description,
                    debit=line.debit,
                    credit=line.credit,
                )
            record_audit(
                user, "journal.posted", "journals", entry.id,
                {"entry_number": entry.entry_number, "entry_date": entry.entry_date, "total": str(debit), "line_count": len(payload.lines)},
            )
            return _entry_payload(entry)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/reports/accounting-summary")
def accounting_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user=Depends(require_permission("reports", "read")),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="بازهٔ گزارش معتبر نیست.")
    as_of = end_date or date.today()

    def aggregate(start=None, end=None, exclude_closing=False):
        query = (
            JournalLine.select(
                LedgerAccount.id.alias("account_id"),
                LedgerAccount.code.alias("code"),
                LedgerAccount.name.alias("name"),
                LedgerAccount.account_type.alias("account_type"),
                fn.COALESCE(fn.SUM(JournalLine.debit), 0).alias("debit"),
                fn.COALESCE(fn.SUM(JournalLine.credit), 0).alias("credit"),
            )
            .join(LedgerAccount)
            .switch(JournalLine)
            .join(JournalEntry)
            .where(JournalEntry.status == "posted")
        )
        if start is not None:
            query = query.where(JournalEntry.entry_date >= start)
        if end is not None:
            query = query.where(JournalEntry.entry_date <= end)
        if exclude_closing:
            query = query.where(JournalEntry.is_year_closing == False)
        return list(query.group_by(LedgerAccount.id).order_by(LedgerAccount.code).dicts())

    def money_rows(rows):
        result = []
        for row in rows:
            debit = Decimal(str(row["debit"] or 0)).quantize(Decimal("0.01"))
            credit = Decimal(str(row["credit"] or 0)).quantize(Decimal("0.01"))
            result.append({
                "account_id": str(row["account_id"]),
                "code": row["code"],
                "name": row["name"],
                "account_type": row["account_type"],
                "debit": str(debit),
                "credit": str(credit),
                "net": str(debit - credit),
            })
        return result

    with DBManager():
        _seed_chart()
        # The trial balance is the selected-period movement, including closing journals.
        activity_rows = aggregate(start_date, end_date, exclude_closing=False)
        accounts = money_rows(activity_rows)
        total_debit = sum((Decimal(row["debit"]) for row in accounts), Decimal("0"))
        total_credit = sum((Decimal(row["credit"]) for row in accounts), Decimal("0"))

        # The profit-and-loss statement excludes closing entries so closed years still
        # report their original revenue and expense rather than artificial zeros.
        pnl_rows = money_rows(aggregate(start_date, end_date, exclude_closing=True))
        income = sum(
            (Decimal(row["credit"]) - Decimal(row["debit"]) for row in pnl_rows if row["account_type"] == "income"),
            Decimal("0"),
        )
        expenses = sum(
            (Decimal(row["debit"]) - Decimal(row["credit"]) for row in pnl_rows if row["account_type"] == "expense"),
            Decimal("0"),
        )

        # A balance sheet is cumulative through the selected end date, not just activity
        # inside the report's start/end window.
        balance_rows = money_rows(aggregate(None, as_of, exclude_closing=False))
        assets = sum(
            (Decimal(row["debit"]) - Decimal(row["credit"]) for row in balance_rows if row["account_type"] == "asset"),
            Decimal("0"),
        )
        liabilities_equity = sum(
            (Decimal(row["credit"]) - Decimal(row["debit"]) for row in balance_rows if row["account_type"] in ("liability", "equity")),
            Decimal("0"),
        )

        # Profit already transferred into retained earnings by posted year-close entries
        # must not be added to equity again. Add only P&L activity in currently open periods.
        unclosed_query = (
            JournalLine.select(
                LedgerAccount.account_type.alias("account_type"),
                fn.COALESCE(fn.SUM(JournalLine.debit), 0).alias("debit"),
                fn.COALESCE(fn.SUM(JournalLine.credit), 0).alias("credit"),
            )
            .join(LedgerAccount)
            .switch(JournalLine)
            .join(JournalEntry)
            .where(
                (JournalEntry.status == "posted")
                & (JournalEntry.is_year_closing == False)
                & (JournalEntry.entry_date <= as_of)
                & (LedgerAccount.account_type.in_(("income", "expense")))
            )
        )
        closed_years = list(
            FiscalYear.select().where(
                (FiscalYear.status == "closed") & (FiscalYear.end_date <= as_of)
            )
        )
        for fiscal in closed_years:
            unclosed_query = unclosed_query.where(
                ~JournalEntry.entry_date.between(fiscal.start_date, fiscal.end_date)
            )
        unclosed_rows = list(unclosed_query.group_by(LedgerAccount.id).dicts())
        unclosed_income = sum(
            (
                Decimal(str(row["credit"] or 0)) - Decimal(str(row["debit"] or 0))
                for row in unclosed_rows if row["account_type"] == "income"
            ),
            Decimal("0"),
        )
        unclosed_expenses = sum(
            (
                Decimal(str(row["debit"] or 0)) - Decimal(str(row["credit"] or 0))
                for row in unclosed_rows if row["account_type"] == "expense"
            ),
            Decimal("0"),
        )
        unclosed_profit = (unclosed_income - unclosed_expenses).quantize(Decimal("0.01"))
        equity_with_current_profit = liabilities_equity + unclosed_profit

        return {
            "as_of": as_of.isoformat(),
            "accounts": accounts,
            "trial_balance": {
                "debit_total": str(total_debit),
                "credit_total": str(total_credit),
                "balanced": total_debit == total_credit,
            },
            "profit_and_loss": {
                "income": str(income),
                "expenses": str(expenses),
                "net_profit": str(income - expenses),
            },
            "balance_sheet": {
                "assets": str(assets),
                "liabilities_and_equity": str(equity_with_current_profit),
                "unclosed_profit": str(unclosed_profit),
                "difference": str((assets - equity_with_current_profit).quantize(Decimal("0.01"))),
            },
        }


@router.get("/audit")
def list_audit_events(
    response: Response,
    q: Optional[str] = None,
    resource: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_permission("audit", "read")),
):
    with DBManager():
        query = AuditEvent.select()
        if resource:
            query = query.where(AuditEvent.resource == resource)
        if q and q.strip():
            term = q.strip()
            query = query.where(
                AuditEvent.actor_name.contains(term)
                | AuditEvent.action.contains(term)
                | AuditEvent.target_id.contains(term)
            )
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [
            {
                "id": str(item.id),
                "actor_name": item.actor_name,
                "action": item.action,
                "resource": item.resource,
                "target_id": item.target_id,
                "details": json.loads(item.details) if item.details else {},
                "remote_addr": item.remote_addr,
                "created_at": item.created_at.isoformat(),
            }
            for item in query.order_by(AuditEvent.created_at.desc()).paginate(page, page_size)
        ]
