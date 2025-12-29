from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta 
from jose import jwt, JWTError

from app import schemas, database, models 
from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
RESET_PASSWORD_TOKEN_EXPIRE_MINTUES = settings.reset_password_token_expire_minutes
EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = settings.email_verification_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def create_access_token(data: dict, expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({'exp': expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id: str = payload.get("user_id")
        
        if id is None:
            raise credentials_exception
        token_data = schemas.TokenData(id=str(id))
    
    except JWTError:
        raise credentials_exception
    
    return token_data


def create_refresh_token(data: dict, expire_days: int = REFRESH_TOKEN_EXPIRE_DAYS):  
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expire_days)
    to_encode.update({'exp': expire, 'scope': 'refresh_token'})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_refresh_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "refresh_token":
            raise credentials_exception
        id: str = payload.get("user_id")
        if id is None:
            raise credentials_exception
        return schemas.TokenData(id=str(id))
    except JWTError:
        raise credentials_exception


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    
    token = verify_access_token(token, credentials_exception)
    user = db.query(models.User).filter(models.User.id == token.id).first()
    
    if not user:
        raise credentials_exception
    
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email first")
    
    return user 


def create_reset_password_token(user_id: int, expires_minutes: int = RESET_PASSWORD_TOKEN_EXPIRE_MINTUES):
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload = {
        "user_id": user_id,
        "exp": expire,
        "scope": "password_reset",
        
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_reset_password_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("scope") != "password_reset":
            return None
        
        return payload.get("user_id")
    except JWTError:
        return None


def create_email_verification_token(user_id: int, expires_minutes: int = EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES):
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload = {
        "user_id": user_id,
        "exp": expire,
        "scope": "verify_email"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_email_verification_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "verify_email":
            return None
        return payload.get("user_id")
    except JWTError:
        return None
