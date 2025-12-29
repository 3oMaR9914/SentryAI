from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import quote, unquote
from datetime import datetime, timedelta
import requests, json

from app import models
from app.oauth2 import get_current_user
from app.database import get_db
from app.utils import crypt_utils 
from app.config import settings 

router = APIRouter(prefix="/api/integrations/zoom", tags=["Zoom Meetings"])




@router.get("/meetings")
def auth_zoom_meetings(user_id: int = 1):
# def auth_zoom(current_user: models.User=Depends(get_current_user)):
    # user_id = current_user.id
    
    return RedirectResponse(build_zoom_auth_url(user_id=user_id))


@router.get("/callback/meetings")
def zoom_meetings_auth_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state")

    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "zoom_meetings").first()
    if user_integration:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="User already connected before.")

    tokens = get_zoom_tokens(code)
    handle_zoom_token_save(user, tokens, db)

    return {"message": "Zoom access granted successfully", "zoom_tokens": {"access_token": tokens.get("access_token"), "expires_in": tokens.get("expires_in")}}


# @router.get("/meetings/sync")
# def sync_user_zoom_meetings(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
@router.get("/meetings/{user_id}/sync")
def sync_user_zoom_meetings(user_id: int, db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not Found")
    
    integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "zoom_meetings").first()

    if not integration:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Zoom")

    access_token = crypt_utils.decrypt(integration.access_token)
    headers = {"Authorization": f"Bearer {access_token}"}

    url = "https://api.zoom.us/v2/users/me/meetings?type=upcoming"

    res = requests.get(url, headers=headers)

    # refresh token if expired
    if res.status_code == 401:
        token_data = refresh_zoom_access_token(integration, db)
        access_token = token_data["access_token"]
        headers["Authorization"] = f"Bearer {access_token}"
        res = requests.get(url, headers=headers)

    if res.status_code != 200:
        raise HTTPException(500, f"Failed to fetch zoom meetings: {res.json()}")

    meetings = res.json().get("meetings", [])

    for m in meetings:
        meeting_id = str(m["id"])

        task_in_db = db.query(models.Task).filter(models.Task.integration_provider_task_id == meeting_id, models.Task.user_id == user.id).first()

        meeting_start = m.get("start_time")
        meeting_topic = m.get("topic", "Zoom Meeting")
        meeting_status = "Upcoming"
        meeting_updated_at = m.get("updated_at", datetime.utcnow())

        task_data = {
            "title": meeting_topic,
            "description": "Zoom Meeting",
            "deadline": meeting_start,
            "status": meeting_status,
            "category": "Zoom",
            "priority": "Medium",
            "source": "Zoom",
            "updated_at": meeting_updated_at,
            "integration_provider_task_id": meeting_id
        }

        if task_in_db:
            if str(task_in_db.updated_at) != str(meeting_updated_at):
                for key, value in task_data.items():
                    setattr(task_in_db, key, value)
                db.commit()
        else:
            new_task = models.Task(**task_data, user_id=user.id)
            db.add(new_task)
            db.commit()

    return {"message": "Zoom meetings synced successfully."}




def build_zoom_auth_url(user_id: int | None = None) -> str:
    state_data = {}
    if user_id:
        state_data["user_id"] = user_id

    encrypted_state = crypt_utils.encrypt(json.dumps(state_data))
    state = quote(encrypted_state)

    auth_url = (
        f"https://zoom.us/oauth/authorize"
        f"?response_type=code"
        f"&client_id={settings.zoom_client_id}"
        f"&redirect_uri={settings.zoom_redirect_uri()}"
        f"&scope={settings.zoom_mettings_scopes}"
        f"&state={state}"
    )
    return auth_url


def get_zoom_tokens(code: str) -> dict[str, str]:
    url = "https://zoom.us/oauth/token"

    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.zoom_redirect_uri()
    }

    r = requests.post(url, params=params, auth=(settings.zoom_client_id, settings.zoom_client_secret))

    if r.status_code != status.HTTP_200_OK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Zoom token exchange failed: {r.text}")

    data = r.json()
    
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_in": data.get("expires_in")  # seconds
    }


def refresh_zoom_access_token(integration: models.Integration, db: Session):
    url = "https://zoom.us/oauth/token"

    params = {
        "grant_type": "refresh_token",
        "refresh_token": crypt_utils.decrypt(integration.refresh_token)
    }

    request = requests.post(url, params=params, auth=(settings.zoom_client_id, settings.zoom_client_secret))

    if request.status_code != status.HTTP_200_OK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Zoom refresh failed: {request.text}")

    data = request.json()

    integration.access_token = crypt_utils.encrypt(data["access_token"])
    integration.refresh_token = crypt_utils.encrypt(data["refresh_token"])

    if "expires_in" in data:
        integration.expiry = datetime.utcnow() + timedelta(seconds=data["expires_in"])

    db.commit()
    db.refresh(integration)

    return {
        "access_token": data["access_token"]
    }


def handle_zoom_token_save(user: models.User, tokens: dict, db: Session):
    access_token = crypt_utils.encrypt(tokens.get("access_token"))
    
    expires_in = tokens.get("expires_in", 3600)
    expiry_time = datetime.utcnow() + timedelta(seconds=expires_in)
    
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        refresh_token = crypt_utils.encrypt(refresh_token)
    
    new_user_integration = models.Integration(
        user_id = user.id,
        access_token = access_token,
        refresh_token = refresh_token,
        expiry=expiry_time,
        service="zoom_meetings",
    )

    db.add(new_user_integration)
    db.commit()
    db.refresh(new_user_integration)
