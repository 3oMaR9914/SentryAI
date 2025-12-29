from fastapi import APIRouter, Request, HTTPException, status, Depends 
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode, quote, unquote
import json, jwt

from app.database import get_db
from app.config import settings
from app.utils import crypt_utils
from app import models, oauth2



router = APIRouter(prefix="/api/auth/apple", tags=["Apple-Auth"])


@router.get("/login")
async def apple_login():
    return RedirectResponse(url=build_apple_auth_url("login"))


@router.get("/signup")
async def apple_signup():
    return RedirectResponse(url=build_apple_auth_url("signup"))


@router.get("/connect")
async def apple_login(current_user: models.User = Depends(oauth2.get_current_user)):
    return RedirectResponse(url=build_apple_auth_url("signup", current_user.id))

@router.get("/callback/login")
async def apple_login_callback(request: Request, db: Session = Depends(get_db)):
    id_token = request.query_params.get("id_token")
    if not id_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing id_token")

    apple_user = decode_id_token(id_token)
    apple_email = apple_user.get("email")
    
    auth_provider = db.query(models.AuthProvider).filter(models.AuthProvider.provider == "apple", models.AuthProvider.email == apple_email).first()

    if not auth_provider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Apple account not registered")

    return {
        "access_token": oauth2.create_access_token({"user_id": auth_provider.user_id}),
        "refresh_token": oauth2.create_refresh_token({"user_id": auth_provider.user_id}),
        "token_type": "bearer",
        "service_type": "login",
        "apple_user": apple_user
    }


@router.get("/callback/signup")
async def apple_signup_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    id_token = request.query_params.get("id_token")
    
    if not code or not state or not id_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state or id_token")

    apple_user = decode_id_token(id_token)
    apple_email = apple_user.get("email")
    
    existing_auth = db.query(models.AuthProvider).filter(models.AuthProvider.provider == "apple", models.AuthProvider.email == apple_email).first()
    
    if existing_auth:
        raise HTTPException(status.HTTP_409_CONFLICT, "Apple account already registered")
    
    full_name = request.query_params.get("full_name")

    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id", None)
    
    if not user_id:
        if full_name:
            parts = full_name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
        else:
            first_name = ""
            last_name = ""
        
        user = models.User(
            first_name=first_name,
            last_name=last_name,
            birthday = None,
            is_verified=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        
        user_id = user.id
    
    auth_provider = models.AuthProvider(
        user_id=user_id,
        provider="apple",
        email=apple_email,
    )

    db.add(auth_provider)
    db.commit()
    db.refresh(auth_provider)

    return {
        "access_token": oauth2.create_access_token({"user_id": user.id}),
        "refresh_token": oauth2.create_refresh_token({"user_id": user.id}),
        "token_type": "bearer",
        "service_type": "signup",
        "apple_user": apple_user
    }


def build_apple_auth_url(service_type: str, user_id: int | None = None):
    state_data = {"service_type": service_type}
    
    if user_id:
        state_data["user_id"] = user_id
        
    encrypted_state = crypt_utils.encrypt(json.dumps(state_data))
    state = quote(encrypted_state)
    
    params = {
        "client_id": settings.apple_client_id,
        "redirect_uri": settings.apple_redirect_uri(service_type),
        "response_type": "code id_token",
        "scope": "name email",
        "response_mode": "form_post",
        "state": state
    }
    return f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"


def decode_id_token(id_token: str):
    try:
        decoded = jwt.decode(id_token, options={"verify_signature": False})
        return decoded
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid id_token")

