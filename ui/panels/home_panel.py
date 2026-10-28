from datetime import datetime, date, time
from PySide2.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGridLayout, QFrame,
    QGraphicsDropShadowEffect, QSizePolicy, QPushButton, QHBoxLayout
)
from PySide2.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve
from PySide2.QtGui import QColor, QCursor
from peewee import fn

from manager.db import DBManager
from db.models import User, Product, Category, Receipt
import random

class Home(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.setStyleSheet("background-color: transparent;")

        # — Welcome label —
        self.lbl_welcome = QLabel("خوش آمدید", alignment=Qt.AlignCenter)
        self.lbl_welcome.setStyleSheet("font-size:24px; font-weight:bold; color:#333;")
        self.lbl_welcome.setContentsMargins(0, 20, 0, 20)

        # — Refresh button —
        self.btn_refresh = QPushButton("رفرش")
        self.btn_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_refresh.clicked.connect(self.refresh)

        # put welcome + refresh side by side
        hdr_layout = QHBoxLayout()
        hdr_layout.addWidget(self.lbl_welcome, stretch=1)
        hdr_layout.addWidget(self.btn_refresh)

        # — Metric cards —
        self.card_users        = self._make_card("کاربران امروز",     "0")
        self.card_products     = self._make_card("محصولات امروز",     "0")
        self.card_categories   = self._make_card("دسته‌بندی‌های امروز", "0")
        self.card_receipts     = self._make_card("فاکتورهای امروز",   "0")
        self.card_paid_sales   = self._make_card("مجموع فروش نقدی امروز",   "0")
        self.card_unpaid_sales = self._make_card("مجموع فروش نسیه امروز",    "0")

        cards_layout = QGridLayout()
        cards_layout.setContentsMargins(40, 0, 40, 0)
        cards_layout.setHorizontalSpacing(30)
        cards_layout.setVerticalSpacing(30)

        self.cards = [
            self.card_users,
            self.card_products,
            self.card_categories,
            self.card_receipts,
            self.card_paid_sales,
            self.card_unpaid_sales,
        ]
        for i, card in enumerate(self.cards):
            cards_layout.addWidget(card, i // 2, i % 2)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        main_layout.addLayout(hdr_layout)
        main_layout.addLayout(cards_layout)
        main_layout.addStretch()

        # initial load
        self.refresh()

        # hover effects
        for card in self.cards:
            card.installEventFilter(self)

    def _make_card(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setFixedSize(280, 140)
        frame.setCursor(QCursor(Qt.PointingHandCursor))
        frame.setStyleSheet("""
            QFrame { background:#444; border-radius:8px; }
            QLabel#title { font-size:18px; color:#eee; }
            QLabel#value { font-size:36px; font-weight:bold; color:#fff; }
        """)

       
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(10)
        shadow.setColor(Qt.black)
        shadow.setOffset(0, 0)
        frame.setGraphicsEffect(shadow)

        
        anim = QPropertyAnimation(shadow, b"blurRadius", frame)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        frame._shadow = shadow
        frame._anim   = anim

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 20)
        lbl_t = QLabel(title, objectName="title")
        lbl_v = QLabel(value, objectName="value")
        layout.addWidget(lbl_t)
        layout.addStretch()
        layout.addWidget(lbl_v, alignment=Qt.AlignRight)
        return frame
    def refresh(self):
        
        now = datetime.now()
        today_start = datetime.combine(date.today(), time.min)

        with DBManager():
            new_users = User.select().where(
                (User.created_at >= today_start) & (User.created_at <= now)
            ).count()

            new_products = Product.select().where(
                (Product.created_at >= today_start) & (Product.created_at <= now)
            ).count()

            new_categories = Category.select().where(
                (Category.created_at >= today_start) & (Category.created_at <= now)
            ).count()

            today_receipts = Receipt.select().where(
                (Receipt.created_at >= today_start) & (Receipt.created_at <= now)
            ).count()

            paid_sales = (
                Receipt
                .select(fn.SUM(Receipt.total_price).alias("sum"))
                .where(
                    Receipt.payed == True,
                    (Receipt.created_at >= today_start) & (Receipt.created_at <= now)
                )
                .scalar() or 0
            )

            unpaid_sales = (
                Receipt
                .select(fn.SUM(Receipt.total_price).alias("sum"))
                .where(
                    Receipt.payed == False,
                    (Receipt.created_at >= today_start) & (Receipt.created_at <= now)
                )
                .scalar() or 0
            )

    
        self.card_users.findChild(QLabel, "value").setText(str(new_users))
        self.card_products.findChild(QLabel, "value").setText(str(new_products))
        self.card_categories.findChild(QLabel, "value").setText(str(new_categories))
        self.card_receipts.findChild(QLabel, "value").setText(str(today_receipts))
        self.card_paid_sales.findChild(QLabel, "value").setText(f"{paid_sales:,.2f}")
        self.card_unpaid_sales.findChild(QLabel, "value").setText(f"{unpaid_sales:,.2f}")

    def eventFilter(self, source, event):
        cards = [
            self.card_users,
            self.card_products,
            self.card_categories,
            self.card_receipts,
            self.card_paid_sales,
            self.card_unpaid_sales,
        ]
        if source in cards:
            if event.type() == QEvent.Enter:
                source._anim.stop()
                source._anim.setEndValue(20)
                source._anim.start()
                color = QColor.fromHsvF(random.random(), 0.6, 0.8).name()
                self.lbl_welcome.setStyleSheet(
                    f"font-size:24px; font-weight:bold; color:{color};"
                )
            elif event.type() == QEvent.Leave:
                source._anim.stop()
                source._anim.setEndValue(8)
                source._anim.start()
                self.lbl_welcome.setStyleSheet(
                    "font-size:24px; font-weight:bold; color:#333;"
                )
        return super().eventFilter(source, event)
    def card_visibility(self, v:bool):
        for card in self.cards:
            card.setVisible(v)
        self.btn_refresh.setVisible(v)