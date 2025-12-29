from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import unquote
import json 

from app.database import get_db
from app.utils import google_utils, crypt_utils
from app import models, oauth2



router = APIRouter(prefix="/api/auth/google", tags=["Google-Auth"])


@router.get("/login")
async def google_login():
    return RedirectResponse(url=google_utils.build_google_auth_url("login", is_only_login=True))


@router.get("/signup")
async def google_signup():
    return RedirectResponse(url=google_utils.build_google_auth_url("signup"))


@router.get("/connect")
async def google_connect(current_user: models.User = Depends(oauth2.get_current_user)):
    return RedirectResponse(url=google_utils.build_google_auth_url("signup", current_user.id)) 


@router.get("/callback/login")
async def google_login_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state")

    tokens = google_utils.get_google_tokens(code, "login")
    user_info = google_utils.get_google_user_info(tokens["access_token"])
    
    google_email = user_info.get("email") 

    auth = db.query(models.AuthProvider).filter(models.AuthProvider.provider == "google", models.AuthProvider.email == google_email).first()
    
    if not auth:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This Google account has not signed up yet.")

    return {
        "access_token": oauth2.create_access_token({"user_id": auth .user_id}),
        "refresh_token": oauth2.create_refresh_token({"user_id": auth.user_id}),
        "token_type": "bearer",
        "service_type": "login",
        "google_user": user_info,
    }


@router.get("/callback/signup")
async def google_signup_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state")
    

    tokens = google_utils.get_google_tokens(code, "signup")
    user_info = google_utils.get_google_user_info(tokens["access_token"])
    
    google_email = user_info.get("email")

    existing_provider = db.query(models.AuthProvider).filter(models.AuthProvider.provider == "google", models.AuthProvider.email == google_email).first()
    
    if existing_provider:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    
    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id", None)
    
    if not user_id:
        birthday = google_utils.get_google_birthday(tokens["access_token"])
        user = models.User(
            first_name=user_info.get("given_name"),
            last_name=user_info.get("family_name"),
            birthday=birthday,
            is_verified=True,
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        user_id = user.id
    
    
    auth_provider = models.AuthProvider(
        email = google_email,
        user_id = user_id,
        provider = "google",
    )
    
    db.add(auth_provider)
    db.commit()
    db.refresh(auth_provider)
    
    return {
        "access_token": oauth2.create_access_token({"user_id": user.id}),
        "refresh_token": oauth2.create_refresh_token({"user_id": user.id}),
        "token_type": "bearer",
        "service_type": "signup",
        "google_user": user_info,
    }

