from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import quote, unquote
import requests, json, datetime, base64

from app import models
from app.oauth2 import get_current_user
from app.database import get_db
from app.utils import crypt_utils 
from app.config import settings 

router = APIRouter(prefix="/api/integrations/zoom", tags=["Zoom-Auth"])

@router.get("/auth")
def auth_zoom_meetings(user_id: int = 1):
# def auth_zoom(current_user: models.User=Depends(get_current_user)):
    # user_id = current_user.id
    
    return RedirectResponse(url=build_zoom_auth_url(user_id=user_id))


@router.get("/callback")
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
    b64_auth = base64.b64encode(f"{settings.zoom_client_id}:{settings.zoom_client_secret}".encode()).decode()

    resp = requests.post("https://zoom.us/oauth/token",
        params={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.zoom_redirect_uri()}
        , headers={"Authorization": f"Basic {b64_auth}"}
        , timeout=10
    )
    
    if not resp.ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Failed to get token from Zoom")
    return resp.json()


def handle_zoom_token_save(user: models.User, tokens: dict, db: Session):
    access_token = crypt_utils.encrypt(tokens.get("access_token"))
    
    expires_in = tokens.get("expires_in", 3600)
    expiry_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
    
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
