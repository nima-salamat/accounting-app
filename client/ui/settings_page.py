"""Client settings and session controls."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QLineEdit,QPushButton,QVBoxLayout,QComboBox


class SettingsPage(QFrame):
    def __init__(self,window):
        super().__init__();self.window=window
        self.setObjectName("Card");self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,22,22,22);layout.setSpacing(16)
        title=QLabel("تنظیمات");title.setObjectName("PageTitle")
        subtitle=QLabel("تنظیم ارتباط کلاینت با سرور و ظاهر برنامه.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title);layout.addWidget(subtitle)
        card=QFrame();card.setObjectName("Card");form=QVBoxLayout(card);form.setContentsMargins(18,18,18,18)
        form.addWidget(QLabel("نشانی API"))
        self.url=QLineEdit(window.api.base_url if window.api else "")
        form.addWidget(self.url)
        self.save_button=QPushButton("ذخیره و اتصال مجدد");self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.reconnect);form.addWidget(self.save_button)
        layout.addWidget(card)
        theme_card=QFrame();theme_card.setObjectName("Card");theme_layout=QHBoxLayout(theme_card)
        theme_layout.addWidget(QLabel("پوسته"))
        self.theme=QComboBox();self.theme.addItem("روشن","light");self.theme.addItem("تاریک","dark")
        self.theme.setCurrentIndex(1 if window.mode=="dark" else 0)
        self.theme.currentIndexChanged.connect(lambda _i:window.change_theme(self.theme.currentData()))
        theme_layout.addWidget(self.theme,1);layout.addWidget(theme_card)
        info=QLabel("نکات استقرار:\n• API راه دور باید با HTTPS ارائه شود.\n• نصب اولیهٔ راه دور نیازمند ACCOUNTING_APP_SETUP_TOKEN است.\n• برای لغو نشست‌ها از پنل مدیریت نشست‌ها استفاده کنید.")
        info.setObjectName("PageSubtitle");info.setWordWrap(True);layout.addWidget(info);layout.addStretch(1)

    def reconnect(self):
        self.window.connect_to_api(self.url.text().strip())
