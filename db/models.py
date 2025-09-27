from .database import BaseModel
from peewee import (
    CharField,
    FloatField,
    ForeignKeyField,
    BooleanField,
    IntegerField
)
from enum import Enum
from config import FIELD_LENGTH

import hashlib
import binascii
import os
class User(BaseModel):
    username = CharField(max_length=FIELD_LENGTH, unique=True)
    password = CharField(max_length=FIELD_LENGTH
    is_admin = BooleanField(default=False)
    buttons = CharField(max_length=FIELD_LENGTH, default="")

    def set_password(self, password):
        salt = os.urandom(16) 
        pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        self.password = binascii.hexlify(salt + pwdhash).decode('ascii')

    def check_password(self, password):
       
        try:
            stored = binascii.unhexlify(self.password.encode('ascii'))
        except binascii.Error:
           
            return self.password == hashlib.sha256(password.encode()).hexdigest()

        salt = stored[:16]
        stored_pwdhash = stored[16:]
        pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return pwdhash == stored_pwdhash

    def __str__(self):
        return self.username


class Category(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)

    def __str__(self):
        return self.name


class Product(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    buy_price = FloatField(null=False, default=0)
    sell_price = FloatField(null=False, default=0)
    image_path = CharField(max_length=FIELD_LENGTH, null=True)
    custom_product = BooleanField(default=False)
    category = ForeignKeyField(Category, backref="products", null=True, on_delete='SET NULL')
    

    def __str__(self):
        return f"{self.name}"


class Receipt(BaseModel):
    payed = BooleanField(default=False)
    total_price = FloatField(null=False, default=0)
    user = ForeignKeyField(User, backref="receipts", on_delete='CASCADE')
    day_receipt_id = IntegerField(null=False)
    

    def __str__(self):
        return f"{self.id}"


class ReceiptProduct(BaseModel):
    receipt = ForeignKeyField(Receipt, backref="items", on_delete='CASCADE')
    product = ForeignKeyField(Product, backref="receipts", null=True, on_delete='SET NULL')
    buy_price = FloatField(null=False, default=0)
    sell_price = FloatField(null=False, default=0)
    quantity = IntegerField()

    def __str__(self):
        return f"{self.product.name}-{self.quantity}"


class UnitEnum(str, Enum):
    KILOGRAM = 'kg'
    METER = 'm'
    LITRE = 'l'
    PIECE = 'pcs'


class Warehouse(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    price = FloatField(null=False, default=0)
    amount = FloatField(null=False, default=0)
    unit = CharField(choices=[(u.value, u.name) for u in UnitEnum], max_length=10)


class CheckIn(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    check_id = CharField(max_length=FIELD_LENGTH)
    price = FloatField(null=False, default=0)
    date = CharField(max_length=FIELD_LENGTH)
    payed = BooleanField(default=False)

    
class CheckOut(BaseModel):
    name = CharField(max_length=FIELD_LENGTH)
    check_id = CharField(max_length=FIELD_LENGTH)
    price = FloatField(null=False, default=0)
    date = CharField(max_length=FIELD_LENGTH)
    payed = BooleanField(default=False)
