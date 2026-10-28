# برنامه حسابداری 🧮

نرم‌افزار حسابداری دسکتاپ با رابط فارسی، نوشته‌شده با Python و PySide2. داده‌ها در SQLite نگهداری می‌شوند. ساختار کد، تنظیمات، لایهٔ دیتابیس، سرویس‌های دامنه و رابط کاربری را از هم جدا می‌کند.

## قابلیت‌ها

- مدیریت محصولات، دسته‌بندی‌ها، انبار، کاربران، رسیدهای فروش و چک‌ها
- گزارش‌ها، نمودارها، مقایسهٔ بازه‌ها و خروجی CSV/Excel
- رابط فارسی، پوستهٔ روشن و تاریک و محافظ صفحه
- تراکنش‌های اتمیک برای ثبت و ویرایش رسیدها
- پشتیبانی از رمزهای هش‌شدهٔ قدیمی و ارتقای آن‌ها پس از ورود موفق

## پیش‌نیازها

برای سازگاری با رابط فعلی مبتنی بر PySide2، Python 3.9 پیشنهاد می‌شود. وابستگی‌ها در `requirements.txt` فهرست شده‌اند.

## نصب و اجرا

~~~bash
git clone https://github.com/nima-salamat/accounting-app.git
cd accounting-app
python -m venv .venv

# Windows
.venv/Scripts/activate

# Linux / macOS
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
~~~

## ساختار پروژه

~~~text
accounting-app/
├── accounting_app/
│   ├── config.py
│   ├── database/                 # SQLite connection, transactions and models
│   └── services/                 # Authentication, sales, validation and utilities
├── ui/
│   ├── pages/                    # Main window, authentication and dashboard
│   ├── panels/                   # CRUD, sales and reports
│   ├── widgets/                  # Reusable controls and utilities
│   └── styles/
├── manager/                      # Compatibility facades for older imports
├── db/                           # Compatibility facades for older imports
└── tests/                        # Unit and service tests
~~~

## محل ذخیرهٔ داده‌ها

- **Windows:** `%LOCALAPPDATA%/accounting_app/`
- **Linux:** `$XDG_DATA_HOME/accounting_app/`؛ در نبود این متغیر: `~/.local/share/accounting_app/`
- دیتابیس: `app.db`
- تنظیمات رابط: `keys.json`

برای انتخاب مسیر دلخواه از `ACCOUNTING_APP_DATA_DIR` استفاده کنید. مسیر مستقیم دیتابیس با `ACCOUNTING_APP_DB_PATH` قابل تعیین است. پوشه‌ها هنگام import شدن ماژول‌ها ساخته نمی‌شوند؛ برنامه هنگام اجرا پوشهٔ داده را ایجاد می‌کند.

## حساب اولیه و امنیت

در اجرای نخست، اگر حساب مدیر وجود نداشته باشد، حساب `admin` با رمز اولیهٔ `admin` ساخته می‌شود. پس از اولین ورود، رمز عبور پیش‌فرض را تغییر دهید. رمزها با PBKDF2-HMAC-SHA256 و salt تصادفی ذخیره می‌شوند.

## اجرای تست‌ها

~~~bash
python -m unittest discover -s tests -v
python -m compileall -q accounting_app db manager ui main.py config.py
~~~

تست‌ها از دیتابیس موقت استفاده می‌کنند و برای اجرای آن‌ها به راه‌اندازی رابط Qt نیازی نیست.

## پشتیبان‌گیری

پیش از ارتقای نسخه، از فایل `app.db` نسخهٔ پشتیبان تهیه کنید. برای گرفتن نسخهٔ سازگار، برنامه را ببندید تا اتصال SQLite و فایل‌های WAL آزاد شوند.

---

## محیط برنامه 📸

<table>
  <tr>
    <td align="center"><img src="screenshots/login_dark.png" alt="ورود - تاریک" width="520" /></td>
    <td align="center"><img src="screenshots/login_light.png" alt="ورود - روشن" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/home_dark.png" alt="خانه - تاریک" width="520" /></td>
    <td align="center"><img src="screenshots/home_light.png" alt="خانه - روشن" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/screensaver_clock_dark.png" alt="اسکرین‌سیور ساعت - تاریک" width="520" /></td>
   <td align="center"><img src="screenshots/screensaver_ball_light.png" alt="اسکرین‌سیور توپ - روشن" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/user_managment.png" alt="مدیریت کاربران" width="520" /></td>
    <td align="center"><img src="screenshots/user_table.png" alt="جدول کاربران" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/user_table_search_is_admin.png" alt="نتیجه جستجو - admin" width="520" /></td>
    <td align="center"><img src="screenshots/user_table_search_is_not_admin.png" alt="نتیجه جستجو - non-admin" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/add_product.png" alt="افزودن محصول" width="520" /></td>
    <td align="center"><img src="screenshots/add_product_2.png" alt="افزودن محصول - جزئیات" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/sell_1.png" alt="sell page" width="520" /></td>
    <td align="center"><img src="screenshots/sell_2.png" alt="sell page" width="520" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/sell_report_1.png" alt="sell report" width="520" /></td>
    <td align="center"><img src="screenshots/sell_report_2.png" alt="sell report" width="520" /></td>
  </tr>
</table>

