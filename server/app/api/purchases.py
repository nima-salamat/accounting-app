"""Supplier/customer records, purchase invoices, weighted-average stock costing and expenses."""
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from peewee import IntegrityError

from accounting_app.database.connection import DBManager
from accounting_app.database.models import (
    BusinessPartner, ExpenseRecord, JournalEntry, JournalLine, LedgerAccount,
    Product, PurchaseInvoice, PurchaseInvoiceLine, PurchasePayment, StockMovement,
)
from accounting_app.services.accounting_controls import FiscalPeriodClosedError, ensure_period_open
from accounting_app.services.audit import record_audit
from server.app.permissions import require_permission
from server.app.schemas import (
    BusinessPartnerCreate, BusinessPartnerUpdate, ExpenseCreate,
    PurchaseInvoiceCreate, PurchasePaymentCreate,
)

router = APIRouter(tags=["purchasing and expenses"])


def _account(code, name, account_type, description=""):
    item, _created = LedgerAccount.get_or_create(
        code=code,
        defaults={
            "name": name,
            "account_type": account_type,
            "description": description or None,
            "is_active": True,
        },
    )
    return item


def _partner_payload(item):
    return {
        "id": str(item.id), "partner_type": item.partner_type, "name": item.name,
        "phone": item.phone, "email": item.email, "tax_id": item.tax_id,
        "address": item.address, "payment_terms": item.payment_terms,
        "credit_limit": str(item.credit_limit), "is_active": bool(item.is_active),
        "notes": item.notes, "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _invoice_payload(invoice, include_details=True):
    total = Decimal(str(invoice.total_amount))
    paid = Decimal(str(invoice.paid_amount))
    result = {
        "id": str(invoice.id), "supplier_id": str(invoice.supplier_id),
        "supplier_name": invoice.supplier.name, "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "status": invoice.status, "total_amount": str(total), "paid_amount": str(paid),
        "outstanding_amount": str(total - paid), "notes": invoice.notes,
        "created_by_name": invoice.created_by_name,
        "created_at": invoice.created_at.isoformat(),
    }
    if include_details:
        result["items"] = [
            {
                "id": str(line.id),
                "product_id": str(line.product_id) if line.product_id else None,
                "product_name": line.product_name, "description": line.description,
                "quantity": str(line.quantity), "unit_cost": str(line.unit_cost),
                "line_total": str(line.line_total), "stock_tracked": bool(line.stock_tracked),
            }
            for line in PurchaseInvoiceLine.select().where(
                PurchaseInvoiceLine.invoice == invoice.id
            ).order_by(PurchaseInvoiceLine.created_at)
        ]
        result["payments"] = [
            {
                "id": str(payment.id), "amount": str(payment.amount),
                "paid_on": payment.paid_on.isoformat(), "payment_method": payment.payment_method,
                "reference": payment.reference, "notes": payment.notes,
                "operator_name": payment.operator_name,
            }
            for payment in PurchasePayment.select().where(
                PurchasePayment.invoice == invoice.id
            ).order_by(PurchasePayment.paid_on, PurchasePayment.created_at)
        ]
    return result


def _expense_payload(item):
    return {
        "id": str(item.id), "description": item.description, "category": item.category,
        "expense_date": item.expense_date.isoformat(), "amount": str(item.amount),
        "payment_method": item.payment_method, "reference": item.reference,
        "notes": item.notes, "expense_account_id": str(item.expense_account_id),
        "expense_account_name": item.expense_account.name,
        "journal_entry_id": str(item.journal_entry_id) if item.journal_entry_id else None,
        "created_by_name": item.created_by_name, "created_at": item.created_at.isoformat(),
    }


@router.get("/partners")
def list_partners(
    response: Response, q: Optional[str] = None, partner_type: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    _user=Depends(require_permission("partners", "read")),
):
    with DBManager():
        query = BusinessPartner.select()
        if partner_type in ("customer", "supplier"):
            query = query.where(BusinessPartner.partner_type == partner_type)
        if q and q.strip():
            needle = q.strip()
            query = query.where(
                BusinessPartner.name.contains(needle)
                | BusinessPartner.phone.contains(needle)
                | BusinessPartner.email.contains(needle)
                | BusinessPartner.tax_id.contains(needle)
            )
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_partner_payload(item) for item in query.order_by(
            BusinessPartner.name
        ).paginate(page, page_size)]


@router.post("/partners", status_code=status.HTTP_201_CREATED)
def create_partner(payload: BusinessPartnerCreate, user=Depends(require_permission("partners", "create"))):
    with DBManager():
        partner = BusinessPartner.create(
            partner_type=payload.partner_type, name=payload.name.strip(),
            phone=payload.phone.strip() if payload.phone else None,
            email=payload.email.strip() if payload.email else None,
            tax_id=payload.tax_id.strip() if payload.tax_id else None,
            address=payload.address.strip() if payload.address else None,
            payment_terms=payload.payment_terms, credit_limit=payload.credit_limit,
            is_active=payload.is_active, notes=payload.notes,
        )
        record_audit(user, "partner.created", "partners", partner.id,
                     {"partner_type": partner.partner_type, "name": partner.name})
        return _partner_payload(partner)


@router.patch("/partners/{partner_id}")
def update_partner(
    partner_id: UUID, payload: BusinessPartnerUpdate,
    user=Depends(require_permission("partners", "update")),
):
    with DBManager():
        partner = BusinessPartner.get_or_none(BusinessPartner.id == partner_id)
        if partner is None:
            raise HTTPException(status_code=404, detail="طرف حساب پیدا نشد.")
        values = payload.model_dump(exclude_unset=True)
        if "name" in values and values["name"] is not None:
            values["name"] = values["name"].strip()
            if len(values["name"]) < 2:
                raise HTTPException(status_code=422, detail="نام طرف حساب باید حداقل دو نویسه باشد.")
        for key in ("phone", "email", "tax_id", "address"):
            if key in values and isinstance(values[key], str):
                values[key] = values[key].strip() or None
        for key, value in values.items():
            setattr(partner, key, value)
        partner.save()
        record_audit(user, "partner.updated", "partners", partner.id,
                     {"fields": sorted(values), "name": partner.name})
        return _partner_payload(partner)


@router.delete("/partners/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_partner(partner_id: UUID, user=Depends(require_permission("partners", "delete"))):
    with DBManager():
        partner = BusinessPartner.get_or_none(BusinessPartner.id == partner_id)
        if partner is None:
            raise HTTPException(status_code=404, detail="طرف حساب پیدا نشد.")
        if PurchaseInvoice.select().where(PurchaseInvoice.supplier == partner.id).exists():
            raise HTTPException(
                status_code=409,
                detail="این تأمین‌کننده سابقهٔ فاکتور خرید دارد؛ برای حفظ سابقه مالی آن را غیرفعال کنید.",
            )
        record_audit(user, "partner.deleted", "partners", partner.id,
                     {"name": partner.name, "partner_type": partner.partner_type})
        partner.delete_instance()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/purchase-invoices")
def list_purchase_invoices(
    response: Response, q: Optional[str] = None, status_filter: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    _user=Depends(require_permission("purchase_invoices", "read")),
):
    with DBManager():
        query = PurchaseInvoice.select().join(BusinessPartner)
        if q and q.strip():
            needle = q.strip()
            query = query.where(
                PurchaseInvoice.invoice_number.contains(needle)
                | BusinessPartner.name.contains(needle)
            )
        if status_filter in ("posted", "partial", "paid"):
            query = query.where(PurchaseInvoice.status == status_filter)
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_invoice_payload(item, include_details=False) for item in query.order_by(
            PurchaseInvoice.invoice_date.desc(), PurchaseInvoice.created_at.desc()
        ).paginate(page, page_size)]


@router.get("/purchase-invoices/{invoice_id}")
def get_purchase_invoice(
    invoice_id: UUID, _user=Depends(require_permission("purchase_invoices", "read"))
):
    with DBManager():
        invoice = PurchaseInvoice.get_or_none(PurchaseInvoice.id == invoice_id)
        if invoice is None:
            raise HTTPException(status_code=404, detail="فاکتور خرید پیدا نشد.")
        return _invoice_payload(invoice)


@router.post("/purchase-invoices", status_code=status.HTTP_201_CREATED)
def create_purchase_invoice(
    payload: PurchaseInvoiceCreate,
    user=Depends(require_permission("purchase_invoices", "create")),
):
    try:
        with DBManager():
            ensure_period_open(payload.invoice_date, actor=user, action="ثبت فاکتور خرید")
            supplier = BusinessPartner.get_or_none(
                (BusinessPartner.id == payload.supplier_id)
                & (BusinessPartner.partner_type == "supplier")
                & (BusinessPartner.is_active == True)
            )
            if supplier is None:
                raise HTTPException(status_code=422, detail="تأمین‌کننده فعال و معتبر انتخاب کنید.")
            invoice_number = payload.invoice_number.strip()
            if PurchaseInvoice.select().where(
                (PurchaseInvoice.supplier == supplier.id)
                & (PurchaseInvoice.invoice_number == invoice_number)
            ).exists():
                raise HTTPException(status_code=409, detail="این شماره فاکتور قبلاً برای این تأمین‌کننده ثبت شده است.")

            total, stock_total = Decimal("0"), Decimal("0")
            normalized = []
            for item in payload.items:
                product = Product.get_or_none(Product.id == item.product_id) if item.product_id else None
                if item.product_id and product is None:
                    raise HTTPException(status_code=422, detail="یکی از کالاهای انتخاب‌شده پیدا نشد.")
                quantity = Decimal(str(item.quantity)).quantize(Decimal("0.0001"))
                unit_cost = Decimal(str(item.unit_cost)).quantize(Decimal("0.01"))
                line_total = (quantity * unit_cost).quantize(Decimal("0.01"))
                tracked = bool(product is not None and product.track_stock)
                total += line_total
                if tracked:
                    stock_total += line_total
                normalized.append((item, product, quantity, unit_cost, line_total, tracked))

            total = total.quantize(Decimal("0.01"))
            if total <= 0:
                raise HTTPException(status_code=422, detail="جمع فاکتور خرید باید مثبت باشد.")
            invoice = PurchaseInvoice.create(
                supplier=supplier.id, invoice_number=invoice_number,
                invoice_date=payload.invoice_date, due_date=payload.due_date,
                status="posted", total_amount=total, paid_amount=Decimal("0"),
                notes=payload.notes, created_by=user.id, created_by_name=user.username,
            )
            for item, product, quantity, unit_cost, line_total, tracked in normalized:
                product_name = product.name if product is not None else item.description.strip()
                PurchaseInvoiceLine.create(
                    invoice=invoice.id, product=product.id if product is not None else None,
                    product_name=product_name, description=item.description.strip(),
                    quantity=float(quantity), unit_cost=unit_cost, line_total=line_total,
                    stock_tracked=tracked,
                )
                if product is None:
                    continue
                if tracked:
                    before_qty = Decimal(str(product.stock_quantity or 0))
                    before_cost = Decimal(str(product.buy_price or 0))
                    after_qty = before_qty + quantity
                    average_cost = (
                        ((before_qty * before_cost) + (quantity * unit_cost)) / after_qty
                        if after_qty > 0 else unit_cost
                    ).quantize(Decimal("0.0001"))
                    changed = Product.update(
                        stock_quantity=float(after_qty), buy_price=float(average_cost)
                    ).where(
                        (Product.id == product.id)
                        & (Product.stock_quantity == float(before_qty))
                        & (Product.track_stock == True)
                    ).execute()
                    if not changed:
                        raise HTTPException(
                            status_code=409,
                            detail="موجودی کالا هم‌زمان تغییر کرده است؛ فاکتور خرید را ثبت نکنید و وضعیت را بررسی کنید.",
                        )
                    StockMovement.create(
                        product=product.id, user=user.id, performed_by=user.username,
                        quantity_change=float(quantity), stock_before=float(before_qty),
                        stock_after=float(after_qty), reason="purchase",
                        reference_id=str(invoice.id),
                        notes="فاکتور خرید {}؛ بهای واحد {}".format(invoice_number, unit_cost),
                    )
                else:
                    Product.update(buy_price=float(unit_cost)).where(Product.id == product.id).execute()

            inventory = _account("1200", "موجودی کالا", "asset", "موجودی کالا")
            nonstock_expense = _account("6000", "هزینه‌های عملیاتی", "expense", "اقلام غیرانبارشده")
            payable = _account("2000", "حساب‌های پرداختنی", "liability", "بدهی به تأمین‌کنندگان")
            journal = JournalEntry.create(
                entry_number="PUR-{}".format(str(invoice.id).replace("-", "")[:28].upper()),
                entry_date=invoice.invoice_date,
                description="فاکتور خرید {} از {}".format(invoice.invoice_number, supplier.name),
                reference="PURCHASE:{}".format(invoice.id), status="posted",
                created_by=user.id, created_by_name=user.username,
                debit_total=total, credit_total=total,
            )
            if stock_total > 0:
                JournalLine.create(entry=journal.id, account=inventory.id,
                                   description="افزایش موجودی انبار", debit=stock_total, credit=0)
            nonstock_total = (total - stock_total).quantize(Decimal("0.01"))
            if nonstock_total > 0:
                JournalLine.create(entry=journal.id, account=nonstock_expense.id,
                                   description="اقلام خرید غیرانبارشده", debit=nonstock_total, credit=0)
            JournalLine.create(entry=journal.id, account=payable.id,
                               description="بدهی فاکتور خرید به تأمین‌کننده", debit=0, credit=total)
            record_audit(
                user, "purchase_invoice.created", "purchase_invoices", invoice.id,
                {"supplier_id": str(supplier.id), "invoice_number": invoice_number,
                 "total_amount": str(total), "line_count": len(normalized),
                 "stock_total": str(stock_total), "journal_entry_id": str(journal.id),
                 "costing_method": "weighted_average"},
            )
            return _invoice_payload(invoice)
    except FiscalPeriodClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="فاکتور خرید با همین شماره برای این تأمین‌کننده از قبل ثبت شده است.") from exc


@router.post("/purchase-invoices/{invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def add_purchase_payment(
    invoice_id: UUID, payload: PurchasePaymentCreate,
    user=Depends(require_permission("purchase_invoices", "create")),
):
    try:
        with DBManager():
            ensure_period_open(payload.paid_on, actor=user, action="پرداخت فاکتور خرید")
            invoice = PurchaseInvoice.get_or_none(PurchaseInvoice.id == invoice_id)
            if invoice is None:
                raise HTTPException(status_code=404, detail="فاکتور خرید پیدا نشد.")
            outstanding = (Decimal(str(invoice.total_amount)) - Decimal(str(invoice.paid_amount))).quantize(Decimal("0.01"))
            amount = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
            if amount > outstanding:
                raise HTTPException(status_code=409, detail="مبلغ پرداخت از مانده فاکتور بیشتر است: {}".format(outstanding))
            payment = PurchasePayment.create(
                invoice=invoice.id, amount=amount, paid_on=payload.paid_on,
                payment_method=payload.payment_method, reference=payload.reference,
                notes=payload.notes, user=user.id, operator_name=user.username,
            )
            invoice.paid_amount = (Decimal(str(invoice.paid_amount)) + amount).quantize(Decimal("0.01"))
            invoice.status = "paid" if invoice.paid_amount >= Decimal(str(invoice.total_amount)) else "partial"
            invoice.save(only=[PurchaseInvoice.paid_amount, PurchaseInvoice.status, PurchaseInvoice.updated_at])
            payable = _account("2000", "حساب‌های پرداختنی", "liability", "بدهی به تأمین‌کنندگان")
            cash_or_bank = (
                _account("1000", "صندوق نقدی", "asset", "وجوه نقد")
                if payload.payment_method == "cash"
                else _account("1010", "بانک", "asset", "حساب‌های بانکی")
            )
            journal = JournalEntry.create(
                entry_number="PAY-{}".format(str(payment.id).replace("-", "")[:28].upper()),
                entry_date=payload.paid_on,
                description="پرداخت فاکتور {} به {}".format(invoice.invoice_number, invoice.supplier.name),
                reference="PURCHASE-PAYMENT:{}".format(payment.id), status="posted",
                created_by=user.id, created_by_name=user.username,
                debit_total=amount, credit_total=amount,
            )
            JournalLine.create(entry=journal.id, account=payable.id,
                               description="کاهش بدهی تأمین‌کننده", debit=amount, credit=0)
            JournalLine.create(entry=journal.id, account=cash_or_bank.id,
                               description="وجه پرداخت‌شده به تأمین‌کننده", debit=0, credit=amount)
            record_audit(
                user, "purchase_payment.created", "purchase_invoices", invoice.id,
                {"payment_id": str(payment.id), "amount": str(amount), "method": payload.payment_method,
                 "journal_entry_id": str(journal.id), "outstanding_after": str(outstanding - amount)},
            )
            return _invoice_payload(invoice)
    except FiscalPeriodClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/expenses")
def list_expenses(
    response: Response, q: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    _user=Depends(require_permission("expenses", "read")),
):
    with DBManager():
        query = ExpenseRecord.select().join(LedgerAccount)
        if q and q.strip():
            needle = q.strip()
            query = query.where(
                ExpenseRecord.description.contains(needle)
                | ExpenseRecord.category.contains(needle)
                | ExpenseRecord.reference.contains(needle)
            )
        total = query.count()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return [_expense_payload(item) for item in query.order_by(
            ExpenseRecord.expense_date.desc(), ExpenseRecord.created_at.desc()
        ).paginate(page, page_size)]


@router.post("/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(payload: ExpenseCreate, user=Depends(require_permission("expenses", "create"))):
    try:
        with DBManager():
            ensure_period_open(payload.expense_date, actor=user, action="ثبت هزینه")
            if payload.expense_account_id:
                expense_account = LedgerAccount.get_or_none(
                    (LedgerAccount.id == payload.expense_account_id)
                    & (LedgerAccount.account_type == "expense")
                    & (LedgerAccount.is_active == True)
                )
                if expense_account is None:
                    raise HTTPException(status_code=422, detail="حساب هزینهٔ فعال و معتبر انتخاب کنید.")
            else:
                expense_account = _account("6000", "هزینه‌های عملیاتی", "expense", "هزینه‌های جاری")
            amount = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
            if payload.payment_method == "unpaid":
                settlement = _account("2000", "حساب‌های پرداختنی", "liability", "بدهی‌های پرداخت‌نشده")
            elif payload.payment_method == "cash":
                settlement = _account("1000", "صندوق نقدی", "asset", "وجوه نقد")
            else:
                settlement = _account("1010", "بانک", "asset", "حساب‌های بانکی")
            entry = JournalEntry.create(
                entry_number="EXP-{}".format(uuid4().hex[:20].upper()),
                entry_date=payload.expense_date, description=payload.description.strip(),
                reference=("EXP:" + payload.reference.strip()) if payload.reference else None,
                status="posted", created_by=user.id, created_by_name=user.username,
                debit_total=amount, credit_total=amount,
            )
            JournalLine.create(entry=entry.id, account=expense_account.id,
                               description=payload.category, debit=amount, credit=0)
            JournalLine.create(entry=entry.id, account=settlement.id,
                               description="پرداخت هزینه" if payload.payment_method != "unpaid" else "هزینه پرداخت‌نشده",
                               debit=0, credit=amount)
            record = ExpenseRecord.create(
                description=payload.description.strip(), category=payload.category.strip(),
                expense_date=payload.expense_date, amount=amount,
                payment_method=payload.payment_method, reference=payload.reference,
                notes=payload.notes, expense_account=expense_account.id,
                journal_entry=entry.id, created_by=user.id, created_by_name=user.username,
            )
            record_audit(
                user, "expense.created", "expenses", record.id,
                {"amount": str(amount), "category": record.category,
                 "payment_method": payload.payment_method, "journal_entry_id": str(entry.id)},
            )
            return _expense_payload(record)
    except FiscalPeriodClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
