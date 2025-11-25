from fastapi import Depends, status, HTTPException, APIRouter, Response
from sqlalchemy.orm import Session

from app.utils import crypt_utils
from app.database import get_db 
from app import schemas, models, oauth2
from app.utils import email_utils


router = APIRouter(
    prefix = "/api/users",
    tags = ["Users"]
)

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session=Depends(get_db)):
    
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    
    if existing_user:
        if not existing_user .is_verified:
            # send verification email
            verification_token = oauth2.create_email_verification_token(existing_user.id)
            email_utils.send_verification_email(to_email=existing_user.email, token=verification_token)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email already exists but not verified. Verification email resent.")
            
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This email is already registered before.")
    
    hashed_password = crypt_utils.hash(user.password)
    user.password = hashed_password 
    
    new_user = models.User(**user.dict())   
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # send verification email
    verification_token = oauth2.create_email_verification_token(new_user.id)
    email_utils.send_verification_email(to_email=new_user.email, token=verification_token)

    return {"message": "User created. Please check your email to verify your account."}


# public for everyone 
@router.get("/{user_id}", response_model=schemas.UserRead, status_code=status.HTTP_200_OK)
def get_user(user_id: int, db: Session=Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found")
    
    return user 


# require authentication (login)
@router.put("/", response_model=schemas.UserRead, status_code=status.HTTP_200_OK)
def edit_user(updated_user: schemas.UserCreate, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    
    user_query = db.query(models.User).filter(models.User.id == current_user.id)
    user_query.update(updated_user.dict(), synchronize_session=False)
    db.commit()
    
    return user_query.first()


# require authentication (login)
@router.delete("/", response_model=schemas.TaskRead)
def delete_user(db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    
    user_query = db.query(models.User).filter(models.User.id == current_user.id)    
    user_query.delete(synchronize_session=False)
    db.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
