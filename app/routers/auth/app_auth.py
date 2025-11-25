from fastapi import Depends, status, HTTPException, APIRouter
from fastapi.security import OAuth2PasswordRequestForm 
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app import schemas, models, oauth2
from app.utils import crypt_utils
from app.utils.email_utils import send_reset_email
from app.database import get_db 


router = APIRouter(prefix="/api/auth", tags=["App-Auth"])


@router.post('/login', response_model=schemas.Token, status_code=status.HTTP_200_OK)
def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.email == user_credentials.username).first()
    
    if not user or not user.password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invaild Credentials")

    if not crypt_utils.verify(user_credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials")
    
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email first from your mailbox.")

    access_token = oauth2.create_access_token(data = {"user_id": user.id})
    refresh_token = oauth2.create_refresh_token(data={"user_id": user.id})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post('/logout')
def logout(current_user: models.User = Depends(oauth2.get_current_user), db: Session = Depends(get_db)):
    current_user.refresh_token = None
    current_user.refresh_token_expiry = None
    db.commit()
    return {"detail": "Logged out successfully"}


@router.post('/refresh-token', status_code=status.HTTP_200_OK)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    token_data = oauth2.verify_refresh_token(refresh_token, credentials_exception)
    
    user = db.query(models.User).filter(models.User.id == token_data.id).first()
    if not user or not user.refresh_token or not crypt_utils.verify(refresh_token, user.refresh_token):
        raise credentials_exception

    if not crypt_utils.verify(refresh_token, user.refresh_token):
            raise credentials_exception

    if user.refresh_token_expiry and user.refresh_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    new_refresh_token = oauth2.create_refresh_token(data={"user_id": user.id})
    user.refresh_token = crypt_utils.hash(new_refresh_token)
    user.refresh_token_expiry = datetime.utcnow() + timedelta(days=7)
    db.commit()

    new_access_token = oauth2.create_access_token(data={"user_id": user.id})
    
    # TODO i want to put here sync_all_user_integration_data func 
    # as for every refresh tokens get all also refresh it's data  
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


@router.post("/forgot-password")
def forgot_password(email: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        token = oauth2.create_reset_password_token(user.id)
        send_reset_email(user.email, token)

    return {"msg": "If this email exists, a reset link was sent."}


@router.post("/reset-password")
def reset_password(token: str, new_password: str, db: Session = Depends(get_db)):
    user_id = oauth2.verify_reset_password_token(token)
    
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    user.password = crypt_utils.hash(new_password)
    db.commit()
    
    return {"msg": "Password updated successfully"}


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user_id = oauth2.verify_email_verification_token(token)
    
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    
    if user.is_verified:
        return {"message": "Email already verified."}
    
    user.is_verified = True
    db.commit()

    access_token = oauth2.create_access_token({"user_id": user.id})
    refresh_token = oauth2.create_refresh_token(data={"user_id": user.id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        }

