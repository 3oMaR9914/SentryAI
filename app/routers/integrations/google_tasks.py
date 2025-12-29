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

router = APIRouter(prefix="/api/integrations/google", tags=["Google Tasks"])


@router.get("/tasks")
async def auth_tasks(current_user_id: int = 1):
# async def auth_tasks(current_user=Depends(get_current_user)):
    # current_user_id = current_user.id
    
    return RedirectResponse(google_utils.build_google_auth_url("tasks",user_id=current_user_id,scopes=settings.google_tasks_scopes))


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
    
    google_utils.handle_token_save(user, tokens, db, "google_tasks")

    return {"message": "Google Tasks connected"}


# @router.get("/tasks/sync")
# def sync_user_google_tasks(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
#     user_id = current_user.id
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

    if res.status_code != status.HTTP_200_OK:
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
                task_in_db = db.query(models.Task).filter(models.Task.integration_provider_task_id == t["id"], models.Task.user_id == user.id).first()
                
                task_data = {
                    "title"             : t.get("title", "Untitled"),
                    "description"       : t.get("notes", ""),
                    "deadline"          : t.get("due", datetime.utcnow()),
                    
                    "status"            : "Completed" if t.get("status")=="completed" else "In progress",
                    "category"          : "General",  # General as default #############################################################
                    "priority"          : "Medium",   #  medium as default #############################################################
                    
                    "source"            : "Google Tasks",
                    "updated_at"        : t.get("updated"),
                    "integration_provider_task_id"    : t["id"],
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

