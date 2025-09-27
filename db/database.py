from peewee import DatabaseProxy, Model, UUIDField, DateTimeField
from datetime import datetime
from config import DATABASE
import uuid


class DB:
    @staticmethod
    def get_default_data_base():
        return DATABASE["DEFAULT"]["NAME"]
    @staticmethod
    def get_data_base(name):
        DATABASE["DEFAULT"][name]
        

# db_name = DB.get_default_data_base()
# db = SqliteDatabase(db_name)
db = DatabaseProxy()

class BaseModel(Model):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)
    class Meta:
        database = db
    
    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)