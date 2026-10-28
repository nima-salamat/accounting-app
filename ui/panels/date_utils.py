"""Jalali date conversion utilities shared by UI and data workers."""
from datetime import datetime, date, timedelta

import jdatetime

JalaliDatetime = jdatetime.datetime
JalaliDate = jdatetime.date

def to_jalali(dt):
    if isinstance(dt, datetime):
        return JalaliDatetime.fromgregorian(datetime=dt).strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(dt, date):
        return JalaliDate.fromgregorian(date=dt).strftime('%Y-%m-%d')
    return dt

def jalali_tomorrow_date():
    j_today = jdatetime.date.today()

    g_today = j_today.togregorian()

    g_tomorrow = g_today + timedelta(days=1)

    j_tomorrow = jdatetime.date.fromgregorian(date=g_tomorrow)
    
    return j_tomorrow
def from_jalali(jalali_str, is_datetime=False):
    try:
        if is_datetime:
            if len(jalali_str.strip()) == 16:  # مثل "1403-04-13 01:05"
                jalali_str += ":00"
            jalali_dt = JalaliDatetime.strptime(jalali_str, '%Y-%m-%d %H:%M:%S')
            return jalali_dt.togregorian()
        else:
            jalali_date = JalaliDate.strptime(jalali_str, '%Y-%m-%d')
            return jalali_date.togregorian()
    except ValueError:
        raise ValueError(f"فرمت تاریخ شمسی نامعتبر است: {jalali_str}")

def parse_jalali_datetime(date_str, time_str):
    if not date_str or not time_str:
        return None
    try:
        year, month, day = map(int, date_str.split('/'))
        parts = list(map(int, time_str.split(':')))
        hour = parts[0]
        minute = parts[1] if len(parts) > 1 else 0
        second = parts[2] if len(parts) > 2 else 0
        jalali_date = JalaliDate(year, month, day)
        g_date = jalali_date.togregorian()
        return datetime(g_date.year, g_date.month, g_date.day, hour, minute, second)
    except Exception as e:
        raise ValueError(f"خطا در تبدیل تاریخ و زمان: {e}")


# Worker classes for threading
