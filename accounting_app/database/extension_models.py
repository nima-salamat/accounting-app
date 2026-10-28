"""Metadata tables for extensible entities and custom fields."""
from peewee import BooleanField, CharField, TextField

from accounting_app.database.connection import BaseModel


class AppSetting(BaseModel):
    key = CharField(max_length=128, unique=True)
    value = TextField(default="")

    class Meta:
        table_name = "app_settings"


class CustomModelDefinition(BaseModel):
    model_key = CharField(max_length=64, unique=True)
    label = CharField(max_length=256)

    class Meta:
        table_name = "custom_model_definitions"


class CustomFieldDefinition(BaseModel):
    entity_type = CharField(max_length=64)
    field_key = CharField(max_length=64)
    label = CharField(max_length=256)
    field_type = CharField(max_length=16, default="text")
    is_required = BooleanField(default=False)

    class Meta:
        table_name = "custom_field_definitions"
        indexes = ((("entity_type", "field_key"), True),)


class CustomFieldValue(BaseModel):
    entity_type = CharField(max_length=64)
    record_id = CharField(max_length=64)
    field_key = CharField(max_length=64)
    value = TextField(null=True)

    class Meta:
        table_name = "custom_field_values"
        indexes = ((("entity_type", "record_id", "field_key"), True),)


class CustomRecord(BaseModel):
    entity_type = CharField(max_length=64, index=True)
    data = TextField(default="{}")

    class Meta:
        table_name = "custom_records"
