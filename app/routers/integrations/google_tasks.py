from fastapi import APIRouter, Depends, Request,HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
from urllib.parse import unquote
import json, requests


from app.config import settings
from app import models
from app.database import get_db
from app.utils import crypt_utils, google_utils
from app.oauth2 import get_current_user

router = APIRouter(prefix="/api/integrations/google", tags=["Google Data"])


@router.get("/calendar")
async def auth_calendar(current_user_id: int = 1):
# async def auth_calendar(current_user=Depends(get_current_user)):
    # current_user_id = current_user.id
    
    return RedirectResponse(url=google_utils.build_google_auth_url("calendar", user_id=current_user_id, scopes=settings.google_calendar_scopes))


@router.get("/tasks")
async def auth_tasks(current_user_id: int = 1):
# async def auth_tasks(current_user=Depends(get_current_user)):
    # current_user_id = current_user.id
    
    return RedirectResponse(google_utils.build_google_auth_url("tasks",user_id=current_user_id,scopes=settings.google_tasks_scopes))



@router.get("/callback/calendar")
async def calendar_auth_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state")

    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "google_calendar").first()
    if user_integration: 
        raise HTTPException(status.HTTP_409_CONFLICT, "User already connected before.")
    

    tokens = google_utils.get_google_tokens(code, "google_calendar")
    google_utils.handle_token_save(user, tokens, db, "google_calendar")

    return {"message": "Calendar access granted successfully", "google_user": google_utils.get_google_user_info(tokens["access_token"])}


@router.get("/callback/tasks")
async def google_tasks_auth_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing")

    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "google_tasks").first()
    if user_integration: 
        raise HTTPException(status.HTTP_409_CONFLICT, "User already connected before.")

    tokens = google_utils.get_google_tokens(code, "google_tasks")
    google_utils.handle_token_save(user_integration, tokens, db, "google_tasks")

    return {"message": "Google Tasks connected", "google_user": google_utils.get_google_user_info(tokens["access_token"])}



@router.get("/events/{user_id}")
async def get_user_events(user_id: int, db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not Found")
    
    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "google_calendar").first()
    if not user_integration:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Google Calendar")
    
    access_token = crypt_utils.decrypt(user_integration.access_token)
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"maxResults": 10, "singleEvents": True, "orderBy": "startTime"}
    
    res = requests.get("https://www.googleapis.com/calendar/v3/users/me/calendarList",headers=headers, params=params)
    
    if res.status_code == status.HTTP_401_UNAUTHORIZED:
        token_data = google_utils.refresh_google_access_token(user_integration, db, "google_calendar")
        access_token = token_data["access_token"]
        headers["Authorization"] = f"Bearer {access_token}"
        res = requests.get("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers=headers, params=params)
    
    if res.status_code != status.HTTP_200_OK:
        raise HTTPException(res.status_code, res.json())
    
    items = res.json().get("items", []) 
    
    return {"events": items, "total": len(items)}



# @router.get("/tasks/sync")
# def sync_google_tasks(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
@router.get("/tasks/{user_id}/sync")
def sync_user_google_tasks(user_id: int, db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not Found")
    
    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "google_tasks").first()
    if not user_integration:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Google Tasks")
    
    access_token = crypt_utils.decrypt(user_integration.access_token)
    headers = {"Authorization": f"Bearer {access_token}"}

    res = requests.get("https://tasks.googleapis.com/tasks/v1/users/@me/lists", headers=headers)
    if res.status_code == status.HTTP_401_UNAUTHORIZED:
        token_data = google_utils.refresh_google_access_token(user_integration, db, "google_tasks")
        access_token = token_data["access_token"]
        headers["Authorization"] = f"Bearer {access_token}"
        res = requests.get("https://tasks.googleapis.com/tasks/v1/users/@me/lists", headers=headers)

    if res.status_code != 200:
        raise Exception(f"Failed to fetch task lists: {res.json()}")
    
    lists = res.json().get("items", [])
    for tasklist in lists:
        
        list_id = tasklist["id"]

        page_token = None
        while True:
            params = {"maxResults": 250}
            if page_token:
                params["pageToken"] = page_token

            res_tasks = requests.get(f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks", headers=headers, params=params)
            tasks = res_tasks.json().get("items", [])

            for t in tasks:
                task_in_db = db.query(models.Task).filter(models.Task.google_task_id == t["id"], models.Task.user_id == user.id).first()
                
                task_data = {
                    "title"             : t.get("title", "Untitled"),
                    "description"       : t.get("notes", ""),
                    "deadline"          : t.get("due") or datetime.utcnow(),
                    
                    "status"            : "Completed" if t.get("status")=="completed" else "In progress",
                    "category"          : "General",  # General as default #############################################################
                    "priority"          : "Medium",   #  medium as default #############################################################
                    
                    "source"            : "google",
                    "google_task_id"    : t["id"],
                    "google_tasklist_id": list_id,
                    "updated_at"        : t.get("updated")
                }

                if task_in_db:
                    if task_in_db.updated_at != t.get("updated"):
                        for key, value in task_data.items():
                            setattr(task_in_db, key, value)
                        db.commit()
                else:
                    # create new task
                    new_task = models.Task(**task_data, user_id=user.id)
                    db.add(new_task)
                    db.commit()

            page_token = res_tasks.json().get("nextPageToken")
            if not page_token:
                break
            
    return {"message", "Google tasks synced successfully."}



# ======== gmail emails sync emails into db using only ids of the emails

# @router.get("/gmail")
# async def auth_gmail(current_user_id: int = 1):
# # async def auth_gmail(current_user=Depends(get_current_user)):
#         # current_user_id = current_user.id
        
#     return RedirectResponse(url=google_utils.build_google_auth_url("gmail", user_id=current_user_id, scopes=settings.google_gmail_scopes))




# @router.get("/callback/gmail")
# async def gmail_outh_callback(request: Request, db: Session = Depends(get_db)):
#     code = request.query_params.get("code")
#     state = request.query_params.get("state")
    
#     if not code or not state:
#         raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or state")

#     user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id")
#     user = db.query(models.User).filter(models.User.id == user_id).first()
    
#     if not user:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
#     user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "gmail").first()
#     if user_integration: 
#         raise HTTPException(status.HTTP_409_CONFLICT, "User already connected before.")

#     tokens = google_utils.get_google_tokens(code, "gmail")
#     google_utils.handle_token_save(user_integration, tokens, db, "gmail")

#     return {"message": "Gmail access granted successfully", "google_user": google_utils.get_google_user_info(tokens["access_token"])}



# @router.get("/emails/{user_id}")
# async def get_user_emails(user_id: int, db: Session = Depends(get_db)):

#     user = db.query(models.User).filter(models.User.id == user_id).first()
#     if not user:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "User not Found")
    
#     user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "gmail").first()
#     if not user_integration:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Gmail")
    
#     access_token = crypt_utils.decrypt(user_integration.access_token)
#     headers = {"Authorization": f"Bearer {access_token}"}
#     params = {"maxResults": 500, "singleEvents": True, "orderBy": "id"}
    
#     res = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",headers=headers, params=params)
    
#     if res.status_code == status.HTTP_401_UNAUTHORIZED:
#         token_data = google_utils.refresh_google_access_token(user_integration, db, "gmail")
#         access_token = token_data["gmail"]
#         headers["Authorization"] = f"Bearer {access_token}"
#         res = requests.get("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers=headers, params=params)

#     if res.status_code != status.HTTP_200_OK:
#         raise HTTPException(res.status_code, res.json())
    
#     emails = res.json().get("messages", [])

#     return {"emails": emails, "total": len(emails)}


# @router.get("/emails/{user_id}/sync")
# def sync_new_emails(user_id: int, db: Session = Depends(get_db)):
#     user = db.query(models.User).filter(models.User.id == user_id).first()

#     if not user or not user.gmail_access_token or not user.gmail_authorized:
#         raise HTTPException(status.HTTP_403_FORBIDDEN, "User not authorized or connected to Gmail")

#     access_token = crypt_utils.decrypt(user.gmail_access_token)
#     headers = {"Authorization": f"Bearer {access_token}"}

#     # get last fetched email id for this user
#     last_email = db.query(models.GmailEmail).filter(models.GmailEmail.user_id == user_id).order_by(models.GmailEmail.received_at.desc()).first()
#     after_id = last_email.gmail_id if last_email else None

#     params = {"maxResults": 500}

#     # optional: use `q` with after:date to filter new emails
#     if after_id:
#         # we cannot filter by id in Gmail API directly, but can filter by date
#         params["q"] = f"after:{int(last_email.received_at.timestamp())}"

#     # fetch message list
#     res = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
#                         headers=headers, params=params)

#     if res.status_code == status.HTTP_401_UNAUTHORIZED:
#         # refresh token if expired
#         token_data = google_utils.refresh_google_access_token(user_integration, db, "gmail")
#         access_token = token_data["access_token"]
#         headers["Authorization"] = f"Bearer {access_token}"
#         res = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
#                             headers=headers, params=params)

#     if res.status_code != 200:
#         raise HTTPException(res.status_code, res.json())

#     messages = res.json().get("messages", [])
#     new_emails = []

#     for msg in messages:
#         gmail_id = msg["id"]

#         # skip if already exists
#         if db.query(models.GmailEmail).filter_by(gmail_id=gmail_id).first():
#             continue

#         # fetch full message
#         msg_data = google_utils.get_email_contents(gmail_id, access_token)

#         email = models.GmailEmail(
#             user_id=user_id,
#             gmail_id=gmail_id,
#             subject=msg_data.get("subject"),
#             sender=msg_data.get("from"),
#             recipient=msg_data.get("to"),
#             snippet=msg_data.get("snippet"),
#             body=msg_data.get("body"),
#             received_at=datetime.datetime.utcnow()  # or parse from Gmail headers if available
#         )
#         db.add(email)
#         new_emails.append(email)

#     db.commit()
#     return {"new_emails": len(new_emails)}