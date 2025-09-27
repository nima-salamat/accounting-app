from db.models import User
from peewee import DoesNotExist


class AnonymousUser:
    username = None
    
class AuthManager:
    def __init__(self):
        self.user = AnonymousUser()
        self.is_valid = False
        self.errors = []
    
    def validate(self, username, password):
        try:
            self.user = User.get(username= username)
            if self.user.check_password(password):
                self.is_valid = True
            else:
                self.errors.append("Wrong password detected.")

        except DoesNotExist:
            self.errors.append("User does not exists.")
                    
    def __call__(self):
        return self.user

    def is_authenticated(self):
        return self.is_valid

