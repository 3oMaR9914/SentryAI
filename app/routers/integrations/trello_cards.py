from fastapi import APIRouter, Depends, Request,HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from urllib.parse import unquote, quote
import json, requests, time

from app.config import settings
from app import models
from app.database import get_db
from app.utils import crypt_utils
from app.oauth2 import get_current_user
from fastapi_utils.tasks import repeat_every
from app.database import get_db
from datetime import datetime, timedelta


router = APIRouter(prefix="/api/integrations/trello", tags=["Trello Cards"])


@router.on_event("startup")
@repeat_every(seconds=60*60*24)  # Every day remove all tokens that expired (expire here is more than 60 minutes)
def cleanup_temp_tokens_task(minutes: int = 60, db: Session = Depends(get_db)):
    expiry_time = datetime.utcnow() - timedelta(minutes=minutes)
    db.query(models.TempTrelloToken).filter(models.TempTrelloToken.created_at < expiry_time).delete(synchronize_session=False)
    db.commit()


# @router.get("/cards")
# async def auth_trello_cards(current_user_id: int = 1, db: Session = Depends(get_db)):
# # async def auth_cards(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
#     # current_user_id = current_user.id
#     # auth_url = build_trello_auth_url(db, current_user_id)
#     return RedirectResponse(build_trello_auth_url(db, current_user_id))

from requests_oauthlib import OAuth1Session, OAuth1

@router.get("/cards")
def auth_trello_cards(current_user_id: int = 1, db: Session = Depends(get_db)):
    """
    Start Trello OAuth 1.0a flow:
    1) Request a request_token from Trello (with callback)
    2) Save request_token_secret in DB linked to user
    3) Redirect user to Trello authorize URL (with oauth_token)
    """
    # build callback url — must match what you registered in Trello dev dashboard
    callback_url = settings.trello_redirect_uri() # e.g., "https://<ngrok>.ngrok.io/api/integrations/trello/callback/cards"

    # request a temporary token from Trello
    oauth = OAuth1Session(client_key=settings.trello_api_key, client_secret=settings.trello_client_secret, callback_uri=callback_url)
    try:
        fetch_response = oauth.fetch_request_token("https://trello.com/1/OAuthGetRequestToken")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain request token: {e}")

    oauth_token = fetch_response.get("oauth_token")
    oauth_token_secret = fetch_response.get("oauth_token_secret")
    if not oauth_token or not oauth_token_secret:
        raise HTTPException(status_code=500, detail="Invalid request token response from Trello")

    temp = models.TempTrelloToken(
        user_id=current_user_id,
        oauth_token=oauth_token,
        oauth_token_secret=oauth_token_secret,
        created_at=datetime.utcnow()
    )
    db.add(temp)
    db.commit()
    db.refresh(temp)

    auth_url = f"https://trello.com/1/OAuthAuthorizeToken?oauth_token={oauth_token}&name={settings.trello_app_name}&scope=read,write&expiration=never"
    return RedirectResponse(auth_url)


@router.get("/callback/cards")
def trello_callback(request: Request, db: Session = Depends(get_db)):
    """
    Trello will redirect to this endpoint with:
        ?oauth_token=...&oauth_verifier=...
    We:
        - lookup the temp token in DB to get the secret and user_id
        - exchange for access_token
        - store access_token (encrypted) in Integration table
    """
    oauth_token = request.query_params.get("oauth_token")
    oauth_verifier = request.query_params.get("oauth_verifier")

    if not oauth_token or not oauth_verifier:
        raise HTTPException(status_code=400, detail="Missing oauth_token or oauth_verifier")

    # lookup temp token
    temp = db.query(models.TempTrelloToken).filter(models.TempTrelloToken.oauth_token == oauth_token).first()
    if not temp:
        raise HTTPException(status_code=400, detail="Unknown or expired request token")

    # exchange request token + verifier for access token
    oauth = OAuth1Session(
        client_key=settings.trello_api_key,
        client_secret=settings.trello_client_secret,
        resource_owner_key=temp.oauth_token,
        resource_owner_secret=temp.oauth_token_secret,
        verifier=oauth_verifier
                            )
    try:
        access_resp = oauth.fetch_access_token("https://trello.com/1/OAuthGetAccessToken")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch access token: {e}")

    access_token = access_resp.get("oauth_token")
    access_token_secret = access_resp.get("oauth_token_secret")
    if not access_token:
        raise HTTPException(status_code=500, detail="Invalid access token response from Trello")

    # store final access credentials in Integration (encrypt tokens)
    encrypted_token = crypt_utils.encrypt(access_token)
    encrypted_secret = crypt_utils.encrypt(access_token_secret) if access_token_secret else None

    # Optional: ensure user exists
    user = db.query(models.User).filter(models.User.id == temp.user_id).first()
    if not user:
        # cleanup temp and return error
        db.delete(temp)
        db.commit()
        raise HTTPException(status_code=404, detail="User not found")

    # remove any existing trello integration for this user if you want single integration
    db.query(models.Integration).filter(
        models.Integration.user_id == user.id,
        models.Integration.service == "trello_cards"
    ).delete(synchronize_session=False)

    integration = models.Integration(
        user_id=user.id,
        access_token=encrypted_token,
        refresh_token=encrypted_secret,
        expiry=None,
        service="trello_cards"
    )
    db.add(integration)

    # remove temp token record
    db.delete(temp)
    db.commit()
    db.refresh(integration)

    return {"message": "Trello connected successfully"}



# @router.get("/cards/sync")
# def sync_user_trello_cards(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
@router.get("/cards/{user_id}/sync")
def sync_user_trello_cards(user_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "trello_cards").first()
    if not user_integration:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Trello")

    access_token = crypt_utils.decrypt(user_integration.access_token)
    key = settings.trello_api_key
    headers = {"Accept": "application/json"}

    res_boards = requests.get(f"https://api.trello.com/1/members/me/boards?key={key}&token={access_token}", headers=headers)
    boards = res_boards.json()

    for board in boards:
        board_id = board["id"]

        res_cards = requests.get(f"https://api.trello.com/1/boards/{board_id}/cards?key={key}&token={access_token}",headers=headers)
        cards = res_cards.json()

        for card in cards:
            due_date = None
            if card.get("due"):
                due_date = datetime.fromisoformat(card["due"].replace("Z", "+00:00"))

            if card.get("dueComplete"):
                status_value = "Completed"
            elif due_date and datetime.now(timezone.utc) > due_date:
                status_value = "Overdue"
            else:
                status_value = "In progress"

            task_data = {
                "title": card.get("name", "Untitled"),
                "description": card.get("desc", ""),
                "deadline": due_date,
                "status": status_value,
                "category": "Trello",
                "priority": "Medium",
                "source": "Trello",
                # "trello_board_id": board_id,
                "integration_provider_task_id": card["id"],
                "updated_at": card.get("dateLastActivity"),
            }

            task_in_db = db.query(models.Task).filter(models.Task.integration_provider_task_id == card["id"], models.Task.user_id == user.id).first()

            if task_in_db:
                for key, value in task_data.items():
                    setattr(task_in_db, key, value)
            else:
                new_task = models.Task(**task_data, user_id=user.id)
                db.add(new_task)

        db.commit()

    return {"message": "Trello synced successfully for user"}



def build_trello_auth_url(db: Session, user_id: int | None = None) -> str:
    state_data = {"service_type": "trello", "user_id": user_id}
    encrypted_state = crypt_utils.encrypt(json.dumps(state_data))
    state = quote(encrypted_state)

    oauth_token = f"temp_{user_id}_{int(datetime.utcnow().timestamp())}"
    save_temp_trello_token(db, user_id, oauth_token)

    auth_url = (
        f"https://trello.com/1/authorize?"
        f"expiration=never&response_type=token&scope=read,write"
        f"&name={settings.trello_app_name}"
        f"&key={settings.trello_api_key}"
        f"&return_url={settings.trello_redirect_uri()}?state={state}&oauth_token={oauth_token}"
    )
    return auth_url


def save_temp_trello_token(db: Session, user_id: int, oauth_token: str):
    temp = models.TempTrelloToken(
        user_id=user_id,
        oauth_token=oauth_token,
        created_at=datetime.utcnow()
    )
    db.add(temp)
    db.commit()
    db.refresh(temp)
    return temp


def get_trello_tokens(oauth_response: str) -> dict[str, str]:
    # Trello returns token in query string: ?token=XYZ
    token = oauth_response  # in callback, Trello sends ?token=<access_token>
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Failed to get Trello token")
    return {"access_token": token}


def handle_token_save(user: models.User, tokens: dict, db: Session, service: str = "trello"):
    access_token = crypt_utils.encrypt(tokens.get("access_token"))

    new_user_integration = models.Integration(
        user_id=user.id,
        access_token=access_token,
        refresh_token=None,  # Trello token usually doesn't expire
        expiry=None,
        service=service
    )
    db.add(new_user_integration)
    db.commit()
    db.refresh(new_user_integration)

