from fastapi import HTTPException, status
from sqlalchemy.orm import Session 
from urllib.parse import quote
import requests, datetime, json

from app import models
from app.utils import crypt_utils
from app.config import settings 


def get_google_tokens(code: str, service_type) -> dict[str, str]:
    service_type = "calendar" if service_type == "google_calendar" else service_type
    service_type = "tasks" if service_type == "google_tasks" else service_type

    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri(service_type),
        "grant_type": "authorization_code",
    }
    resp = requests.post("https://oauth2.googleapis.com/token", data=data)  
    if not resp.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to get token from Google")
    return resp.json()


def get_google_user_info(access_token: str) -> dict:
    resp = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={"Authorization": f"Bearer {access_token}"})
    
    if not resp.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch Google user info")
    return resp.json()


def get_google_birthday(access_token: str) -> datetime.date | None:
    resp = requests.get("https://people.googleapis.com/v1/people/me?personFields=birthdays", headers={"Authorization": f"Bearer {access_token}"})
    
    if resp.ok:
        data = resp.json()
        if "birthdays" in data:
            bday = data["birthdays"][0].get("date", {})
            year = bday.get("year", 1900)
            month = bday.get("month", 1)
            day = bday.get("day", 1)
            return datetime.date(year, month, day)
    return None


def handle_token_save(user: models.User, tokens: dict, db: Session, service: str):
    access_token = crypt_utils.encrypt(tokens.get("access_token")) 
    
    expires_in = tokens.get("expires_in", 3600)
    expiry_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
    
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        refresh_token =crypt_utils.encrypt(refresh_token)
    
    new_user_integration = models.Integration(
        user_id = user.id,
        access_token=access_token,
        refresh_token = refresh_token,
        expiry=expiry_time,
        service=service)

    db.add(new_user_integration)
    db.commit()
    db.refresh(new_user_integration)



def build_google_auth_url(service_type: str, user_id: int | None = None, scopes: str = None, is_only_login=False) -> str:
    state_data = {"service_type": service_type}
    
    if user_id:
        state_data["user_id"] = user_id
    
    encrypted_state = crypt_utils.encrypt(json.dumps(state_data))
    state = quote(encrypted_state)

    scope = scopes or settings.google_auth_scopes

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={settings.google_client_id}"
        f"&redirect_uri={settings.google_redirect_uri(service_type)}"
        f"&response_type=code&scope={scope}"
        "&access_type=offline"
        f"&state={state}"
    )
    if not is_only_login:
        auth_url += "&prompt=consent"
    
    return auth_url


def get_email_contents(msg_id, user_access_token):
    msg_res = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",headers={"Authorization": f"Bearer {user_access_token}"})
    msg_data = msg_res.json()
    headers_list = msg_data["payload"]["headers"]

    email = {
        "id": msg_id,
        "subject": next((h["value"] for h in headers_list if h["name"] == "Subject"), None),
        "from": next((h["value"] for h in headers_list if h["name"] == "From"), None),
        "to": next((h["value"] for h in headers_list if h["name"] == "To"), None),
        "snippet": msg_data.get("snippet", "")
    }
    
    return email


def refresh_google_access_token(user: models.Integration, db: Session, service: str):
    """
    Refresh Google access token for a specific service (gmail/calendar/tasks).
    Automatically updates the database with the new token and expiry.
    """
    
    try:
        refresh_token = crypt_utils.decrypt(user.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to decrypt {service} refresh token.")

    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        response = requests.post("https://oauth2.googleapis.com/token", data=payload, timeout=10)
    except requests.RequestException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google token endpoint unreachable: {str(e)}")

    if response.status_code != 200:
        if "invalid_grant" in response.text:
            user_query = db.query(models.Integration).filter(models.Integration.id == user.id)
            user_query.delete(synchronize_session=False) 
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"{service.capitalize()} refresh token revoked. Please reconnect your account.")

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to refresh {service} access token: {response.text}")

    token_data = response.json()
    new_access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in", 3600)

    if not new_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No access token returned by Google for {service} service.")

    user.access_token = crypt_utils.encrypt(new_access_token)
    user.expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
    db.commit()
    db.refresh(user)

    return {
        "access_token": new_access_token,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "service": service
    }