from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode, quote, unquote
import json, requests, datetime

from app.database import get_db
from app.utils import crypt_utils
from app.config import settings
from app import models, oauth2


router = APIRouter(prefix="/api/auth/facebook", tags=["Facebook-Auth"])


@router.get("/login")
async def facebook_login():
    return RedirectResponse(url=build_facebook_auth_url("login"))


@router.get("/signup")
async def facebook_signup():
    return RedirectResponse(url=build_facebook_auth_url("signup"))


@router.get("/connect")
async def facebook_connect(current_user: models.User = Depends(oauth2.get_current_user)):
    return RedirectResponse(url=build_facebook_auth_url("signup", current_user.id)) 


@router.get("/callback/login")
async def facebook_login_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code")

    tokens = exchange_code_for_token(code, "login")
    fb_user = get_facebook_user(tokens["access_token"])

    fb_email = fb_user.get("email")
    
    auth = db.query(models.AuthProvider).filter(models.AuthProvider.provider == "facebook", models.AuthProvider.email == fb_email).first()

    if not auth:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Facebook account not registered")

    return {
        "access_token": oauth2.create_access_token({"user_id": auth.user_id}),
        "refresh_token": oauth2.create_refresh_token({"user_id": auth.user_id}),
        "token_type": "bearer",
        "service_type": "login",
        "facebook_user": fb_user
    }


@router.get("/callback/signup")
async def facebook_signup_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state")

    tokens = exchange_code_for_token(code, "signup")
    fb_user = get_facebook_user(tokens["access_token"])

    fb_email = fb_user.get("email")
    
    if not fb_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Facebook email permission is required")

    existing_provider = db.query(models.AuthProvider).filter(models.AuthProvider.provider == "facebook", models.AuthProvider.email == fb_email).first()
    
    if existing_provider:
        raise HTTPException(status.HTTP_409_CONFLICT, "Facebook account already registered")

    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id", None)

    if not user_id:
        first_name = fb_user.get("first_name")
        last_name = fb_user.get("last_name")
        fb_birthday_raw = fb_user.get("birthday") 
        birthday = parse_facebook_birthday(fb_birthday_raw)
        
        user = models.User(
            first_name=first_name,
            last_name=last_name,
            birthday = birthday,
            is_verified=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        
        user_id = user.id
    
    auth_provider = models.AuthProvider(
        user_id = user_id,
        provider = "facebook",
        email = fb_email,
    )

    db.add(auth_provider)
    db.commit()
    db.refresh(auth_provider)
    
    return {
        "access_token": oauth2.create_access_token({"user_id": user.id}),
        "refresh_token": oauth2.create_refresh_token({"user_id": user.id}),
        "token_type": "bearer",
        "service_type": "signup",
        "facebook_user": fb_user
    }



def build_facebook_auth_url(service_type: str, user_id: int | None = None):
    state_data = {"service_type": service_type}
    
    if user_id:
        state_data["user_id"] = user_id
    
    encrypted_state = crypt_utils.encrypt(json.dumps(state_data))
    state = quote(encrypted_state)
    
    params = {
        "client_id": settings.facebook_client_id,
        "redirect_uri": settings.facebook_redirect_uri(service_type),
        "scope": "email,public_profile",
        "response_type": "code",
        "state": state
    }
    return f"https://www.facebook.com/v16.0/dialog/oauth?{urlencode(params)}"


def exchange_code_for_token(code: str, service_type: str):
    params = {
        "client_id": settings.facebook_client_id,
        "redirect_uri": settings.facebook_redirect_uri(service_type),
        "client_secret": settings.facebook_client_secret,
        "code": code
    }
    resp = requests.get("https://graph.facebook.com/v16.0/oauth/access_token", params=params)
    if not resp.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to get token from Facebook")
    return resp.json()


def get_facebook_user(access_token: str):
    fields = "id,first_name,last_name,email"
    resp = requests.get(f"https://graph.facebook.com/me?fields={fields}&access_token={access_token}")
    if not resp.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch Facebook user info")
    return resp.json()


def parse_facebook_birthday(birthday_str: str | None) -> datetime.date | None:
    try:
        parts = birthday_str.split("/")

        if len(parts) == 3:
            month, day, year = parts
            return datetime.date(int(year), int(month), int(day))

        elif len(parts) == 2:
            month, day = parts
            return datetime.date(1900, int(month), int(day))

        else:
            return None

    except Exception:
        return None

