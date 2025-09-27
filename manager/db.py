from peewee import DatabaseProxy, SqliteDatabase

from db.database import DB, db
from db.init_db import create

_db_initialized = False

def initialize_db():
    global _db_initialized
    if not _db_initialized:
        db_path = DB.get_default_data_base()
        real_db = SqliteDatabase(db_path, pragmas={"foreign_keys": 1})
        db.initialize(real_db)
        _db_initialized = True

class DBManager:
    def __enter__(self):
        initialize_db()
        if db.is_closed():
            db.connect()
        db.begin()
        return db

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            db.rollback()
        else:
            db.commit()
        if not db.is_closed():
            db.close()




def create_db():
    with DBManager():
        create(db)
    
def create_admin():
    with DBManager():
        
        from db.models import User
        from peewee import DoesNotExist
        try:
            user = User.get(username="admin")
            user.is_admin = True
            user.save()
        except DoesNotExist: 
            user = User.create(username="admin", password="admin")
            user.is_admin = True
            user.set_password("admin")
            user.save()
        
        
