from passlib.context import CryptContext
from cryptography.fernet import Fernet
from app.config import settings 

pwd_context = CryptContext(schemes=['bcrypt'], deprecated="auto")

def hash(password: str):
    return pwd_context.hash(password)


def verify(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)



secret_key = settings.encryption_key
fernet = Fernet(secret_key.encode())

def encrypt(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()

def decrypt(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()
