# برنامه حسابداری 🧮

## توضیحات 🌠

یک برنامه‌ی سبک حسابداری نوشته‌شده با پایتون و **PySide2** برای مدیریت تراکنش‌ها، حساب‌ها و گزارش‌های پایه. داده‌ها در قالب فایل **SQLite3** ذخیره می‌شوند.

---

## پیش‌نیازها 📦

* پایتون **3.6 – 3.9** (نسخهٔ 3.9 یا پایین‌تر)
  [https://www.python.org/downloads/release/python-390/](https://www.python.org/downloads/release/python-390/)
* فریمورک **PySide2**

```bash
path_to_python_3.9 -m pip install PySide2
```

* کتابخانه **peewee**

```bash
path_to_python_3.9 -m pip install peewee
```

* **SQLite3** (در پایتون گنجانده شده؛ نیازی به نصب جدا نیست)

---

## نصب و اجرا ▶️

```bash
git clone https://github.com/nima-salamat/accounting-app.git
cd accounting-app

# نصب وابستگی‌ها
path_to_python_3.9 -m pip install PySide2
path_to_python_3.9 -m pip install peewee

# اجرا
path_to_python_3.9 main.py
```

---

## مسیر و نام دیتابیس 🗂️

```
%LOCALAPPDATA%\accounting_app\app.db
# مثال:
C:\Users\<User>\AppData\Local\accounting_app\app.db
```

---

## فایل تنظیمات — `config.json` ⚙️

فایل `config.json` برای ذخیره تنظیمات برنامه استفاده می‌شود (مثل حالت تم یا اسکرین‌سیور).

نمونه:

```json
{
  "theme": "dark",
  "screensaver": "ball"
}
```

---

## لاگین پیش‌فرض 🔐

* **نام کاربری:** `admin`
* **رمز عبور:** `admin`

---

## محیط برنامه 📸

<table>
  <tr>
    <td align="center"><img src="screenshots/login_dark.png" alt="ورود - تاریک" width="340" /></td>
    <td align="center"><img src="screenshots/login_light.png" alt="ورود - روشن" width="340" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/home_dark.png" alt="خانه - تاریک" width="340" /></td>
    <td align="center"><img src="screenshots/home_light.png" alt="خانه - روشن" width="340" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/screensaver_ball_dark.png" alt="اسکرین‌سیور توپ - تاریک" width="340" /></td>
    <td align="center"><img src="screenshots/screensaver_ball_light.png" alt="اسکرین‌سیور توپ - روشن" width="340" /></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshots/screensaver_clock_dark.png" alt="اسکرین‌سیور ساعت - تاریک" width="340" /></td>
    <td align="center"><img src="screenshots/screensaver_clock_light.png" alt="اسکرین‌سیور ساعت - روشن" width="340" /></td>
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
    <td align="center"><img src="screenshots/add_product.png" alt="افزودن محصول" width="340" /></td>
    <td align="center"><img src="screenshots/add_product_2.png" alt="افزودن محصول - جزئیات" width="340" /></td>
  </tr>
</table>

