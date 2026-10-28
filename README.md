# برنامه حسابداری 🧮

نرم‌افزار حسابداری دسکتاپ با رابط فارسی، نوشته‌شده با Python و PySide2. داده‌ها در SQLite نگهداری می‌شوند. ساختار کد، تنظیمات، لایهٔ دیتابیس، سرویس‌های دامنه و رابط کاربری را از هم جدا می‌کند.

## قابلیت‌ها

- مدیریت محصولات، دسته‌بندی‌ها، انبار، کاربران، رسیدهای فروش و چک‌ها
- گزارش‌ها، نمودارها، مقایسهٔ بازه‌ها و خروجی CSV/Excel
- رابط فارسی، پوستهٔ روشن و تاریک و محافظ صفحه
- تراکنش‌های اتمیک برای ثبت و ویرایش رسیدها
- پشتیبانی از رمزهای هش‌شدهٔ قدیمی و ارتقای آن‌ها پس از ورود موفق
- نصب‌کنندهٔ مرحله‌ای برای ساخت مدیر با نام کاربری و رمز شخصی، بدون رمز پیش‌فرض
- تعریف مدل‌های سفارشی و فیلدهای تکمیلی برای محصولات، کاربران، رسیدها، انبار، چک‌ها و سایر مدل‌های اصلی

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
│   │   └── extension_models.py   # Custom model/field metadata and values
│   └── services/                 # Authentication, installer, schema registry and domain logic
├── ui/
│   ├── pages/                    # Main window, authentication, dashboard and installer
│   ├── panels/                   # CRUD, custom schemas, sales and reports
│   ├── widgets/                  # Reusable controls and utilities
│   └── styles/
├── manager/                      # Compatibility facades for older imports
├── db/                           # Compatibility facades for older imports
├── server/                       # FastAPI server and versioned API routers
├── client/                       # HTTP client for separate desktop/API integration
└── tests/                        # Unit, service and API tests
~~~

### تفکیک اجزای رابط کاربری

برای آسان‌تر شدن نگهداری، پنل‌های پرحجم به اجزای کوچک‌تر شکسته شده‌اند:

- **فروش:** `sell_panel.py` پوستهٔ اصلی است؛ `sell_catalog_mixin.py`، `sell_checkout_mixin.py`، `sell_workers.py`، `sell_cards.py` و فایل‌های کارت/جست‌وجو، رفتارهای جدا را مدیریت می‌کنند.
- **گزارش‌ها:** `report_panel.py` پنجرهٔ ترکیبی است؛ تب‌های خلاصه، فروش، محصولات، موجودی، دسته‌بندی، پاک‌سازی و چک‌ها در mixinهای مستقل قرار دارند.
- **جدول‌های CRUD:** `base_panel.py` ساختار اصلی جدول را می‌سازد؛ فیلتر و صفحه‌بندی، فرم رکورد، workerهای دیتابیس، ابزار تصویر و خروجی CSV از هم جدا شده‌اند.
- **سرویس‌ها:** تعریف ساختار سفارشی، اعتبارسنجی فیلدها و ذخیرهٔ مقدارها ماژول‌های جدا دارند.

workerهای خواندن گزارش‌ها و برخی عملیات طولانی، خطا را از طریق سیگنال به رابط برمی‌گردانند و اتصال‌های دیتابیس خود را می‌بندند. فایل‌های قدیمی که به‌عنوان import facade باقی مانده‌اند، برای سازگاری با importهای قبلی هستند.

## سرور مستقل FastAPI و کلاینت HTTP

یک سرور مستقل در پوشهٔ **server/** اضافه شده است. رابط API نسخه‌بندی‌شده در **/api/v1** قرار دارد و قراردادهای JSON آن در مستندات OpenAPI قابل مشاهده‌اند.

برای نصب وابستگی‌های سرور و اجرای محلی:

~~~bash
python -m pip install -r server/requirements.txt
python -m server --host 127.0.0.1 --port 8000
~~~

سپس نشانی **http://127.0.0.1:8000/docs** را باز کنید. اگر پایگاه دادهٔ انتخاب‌شده هیچ کاربری نداشته باشد، endpoint **POST /api/v1/setup** برای ساخت مدیر اولیه در دسترس است. در اجراهای بعدی، ورود از **POST /api/v1/auth/login** و هویت کاربر جاری از **GET /api/v1/auth/me** انجام می‌شود.

سرور از متغیر **ACCOUNTING_APP_DB_PATH** برای تعیین فایل SQLite استفاده می‌کند. در حالت پیش‌فرض فقط روی **127.0.0.1** گوش می‌دهد. برای دسترسی از کامپیوترهای دیگر، حداقل یک کلید تصادفی طولانی تعیین کنید و سرور را پشت HTTPS یا یک reverse proxy امن قرار دهید؛ کلید را در مخزن یا کد منبع ذخیره نکنید:

~~~bash
# Generate a secret with Python and set it in the server environment.
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Set ACCOUNTING_APP_SECRET_KEY to the generated value before starting the server.
python -m server --host 0.0.0.0 --port 8000
~~~

برای جلوگیری از چند رسید در اثر تکرار درخواست شبکه، **POST /api/v1/sales** به هدر **Idempotency-Key** نیاز دارد. سرور این کلید را در SQLite ذخیره می‌کند. مشتریانی که نتیجهٔ درخواست در آن‌ها نامشخص شده است باید همان کلید را برای تکرار همان عملیات استفاده کنند.

**client/api_client.py** یک کلاینت HTTP مستقل با timeout، مدیریت خطاها، نشست bearer و متدهای API ارائه می‌کند. درخواست‌های شبکه نباید در thread اصلی Qt اجرا شوند؛ فراخوانی آن از workerها یا یک لایهٔ async کلاینت لازم است.

**وضعیت مهاجرت رابط کاربری:** در این مرحله سرور و قراردادهای API و کتابخانهٔ کلاینت اضافه شده‌اند، اما پنل‌های قدیمی PySide2 هنوز در برخی مسیرها مستقیماً از Peewee و SQLite استفاده می‌کنند. بنابراین، برای استفادهٔ عملی از معماری کاملاً جداشده، لازم است پنل‌ها به‌صورت مرحله‌ای به **AccountingApiClient** منتقل شوند. برنامهٔ دسکتاپ موجود و شیوهٔ اجرای فعلی آن عمداً دست‌نخورده باقی مانده است. سرور فعلی نیز هنوز از SQLite استفاده می‌کند؛ مهاجرت به PostgreSQL تغییر جداگانه‌ای است.

## محل ذخیرهٔ داده‌ها

- **Windows:** `%LOCALAPPDATA%/accounting_app/`
- **Linux:** `$XDG_DATA_HOME/accounting_app/`؛ در نبود این متغیر: `~/.local/share/accounting_app/`
- دیتابیس: `app.db`
- تنظیمات رابط: `keys.json`

برای انتخاب مسیر دلخواه از `ACCOUNTING_APP_DATA_DIR` استفاده کنید. مسیر مستقیم دیتابیس با `ACCOUNTING_APP_DB_PATH` قابل تعیین است. پوشه‌ها هنگام import شدن ماژول‌ها ساخته نمی‌شوند؛ برنامه هنگام اجرا پوشهٔ داده را ایجاد می‌کند.

## نصب اولیه و امنیت

در اجرای اول، به‌جای صفحهٔ ورود یا داشبورد، **نصب‌کنندهٔ مرحله‌ای** نمایش داده می‌شود. در آن نام کاربری و رمز مدیر را تعیین می‌کنید و می‌توانید فیلدهای سفارشی موردنیاز را تعریف کنید. دیگر هیچ حسابی با رمز پیش‌فرض `admin/admin` ساخته نمی‌شود.

در صفحهٔ ساختار داده‌ها، هر ردیف یک فیلد است. کلید مدل باید انگلیسی و با حروف کوچک باشد؛ برای مثال `products` فیلد جدیدی به مدل محصولات اضافه می‌کند، درحالی‌که `contacts` به‌همراه عنوان فارسی و فیلدهایش یک مدل سفارشی می‌سازد. نوع داده و اجباری‌بودن هر فیلد نیز قابل تعیین است.

پس از نصب، مدیر از بخش «ساختارهای سفارشی» می‌تواند مدل یا فیلد جدید اضافه کند، رکوردهای مدل‌های سفارشی را مدیریت کند و برای رکوردهای موجودِ مدل‌های اصلی مقدارهای تکمیلی ذخیره کند. این بخش فقط برای مدیر قابل مشاهده است.

برای سازگاری با داده‌های قبلی، جدول‌های اصلی SQLite حذف یا بازسازی نمی‌شوند. تعریف مدل‌ها و فیلدهای اضافی در جدول‌های فراداده و مقدارها در جدول‌های جدا ذخیره می‌شوند؛ بنابراین هر مدل سفارشی الزاماً یک جدول فیزیکی جدید نمی‌سازد و افزودن فیلد به مدل اصلی به migration مخرب نیاز ندارد. مقادیر فیلدها با نوع تعریف‌شده اعتبارسنجی می‌شوند. حساب‌های موجود در پایگاه‌های نسخه‌های قدیمی نیز بدون نمایش نصب‌کننده حفظ می‌شوند.

رمزهای عبور با PBKDF2-HMAC-SHA256 و salt تصادفی ذخیره می‌شوند.

## اجرای تست‌ها

~~~bash
python -m unittest discover -s tests -v
python -m compileall -q accounting_app db manager ui main.py config.py
~~~

تست‌ها از دیتابیس موقت استفاده می‌کنند و برای اجرای آن‌ها به راه‌اندازی رابط Qt نیازی نیست. در CI، تست‌های واحد و کامپایل ماژول‌های Python روی Python 3.9 و 3.10 اجرا می‌شوند. این بررسی‌ها جای تست دستی رابط گرافیکی و سناریوهای واقعی ویندوز/لینوکس را نمی‌گیرند.

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

