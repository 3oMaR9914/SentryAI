from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from urllib.parse import unquote
import json, requests

from app.config import settings
from app import models
from app.database import get_db
from app.utils import crypt_utils, google_utils
from app.oauth2 import get_current_user


router = APIRouter(prefix="/api/integrations/google", tags=["Google Classroom"])



@router.get("/classroom")
async def auth_classroom(current_user_id: int = 1):
    # async def auth_classroom(current_user=Depends(get_current_user)):
    # current_user_id = current_user.id
    return RedirectResponse(google_utils.build_google_auth_url("classroom", user_id=current_user_id, scopes=settings.google_classroom_scopes))


@router.get("/callback/classroom")
async def google_classroom_auth_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing")

    user_id = json.loads(crypt_utils.decrypt(unquote(state))).get("user_id")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "google_classroom").first()
    if user_integration:
        raise HTTPException(status.HTTP_409_CONFLICT, "User already connected before.")

    tokens = google_utils.get_google_tokens(code, "google_classroom")

    google_utils.handle_token_save(user, tokens, db, "google_classroom")

    return {"message": "Google Classroom connected"}


# @router.get("/classroom/sync")
# def sync_user_google_classroom(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)):
# @router.get("/classroom/{user_id}/sync")
# def sync_user_google_classroom(user_id: int, db: Session = Depends(get_db)):
    
#     user = db.query(models.User).filter(models.User.id == user_id).first()
#     if not user:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "User not Found")

#     user_integration = db.query(models.Integration).filter(models.Integration.user_id == user_id, models.Integration.service == "google_classroom").first()
#     if not user_integration:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Google Classroom")

#     access_token = crypt_utils.decrypt(user_integration.access_token)
#     headers = {"Authorization": f"Bearer {access_token}"}
    
#     courses_res = requests.get("https://classroom.googleapis.com/v1/courses", headers=headers)

#     courses_data = courses_res.json()
#     if "error" in courses_data:
#         raise HTTPException(status.HTTP_400_BAD_REQUEST, courses_data["error"]["message"])
    
#     courses = courses_data.get("courses", [])
    
#     for course in courses:
#         course_id = course["id"]

#         coursework_res = requests.get(f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork?studentId=me", headers=headers)
        
#         coursework_data = coursework_res.json()

#         if "error" in coursework_data:
#             print(f"Coursework API error for course {course_id}: {coursework_data}")
#             continue

#         coursework = coursework_data.get("courseWork", [])
#         if not coursework:
#             print(f"No coursework found for course {course_id}")
        
#         for cw in coursework:
#             work_id = cw["id"]

#             if "dueDate" in cw:
#                 due_date = datetime(
#                     cw["dueDate"]["year"],
#                     cw["dueDate"]["month"],
#                     cw["dueDate"]["day"],
#                     cw.get("dueTime", {}).get("hours", 23),
#                     cw.get("dueTime", {}).get("minutes", 59),
#                     tzinfo=timezone.utc
#                 )
#             else:
#                 due_date = datetime.now()

#             task_data = {
#                 "title": cw.get("title", "Untitled"),
#                 "description": cw.get("description", ""),
#                 "deadline": due_date,
#                 "status": "In progress",
#                 "category": "Classroom",
#                 "priority": "Medium",
#                 "source": "Google Classroom",
#                 "integration_provider_task_id": work_id,
#                 "updated_at": cw.get("updateTime")
#             }

#             task_in_db = db.query(models.Task).filter(models.Task.integration_provider_task_id == work_id,models.Task.user_id == user.id).first()

#             if task_in_db:
#                 for key, value in task_data.items():
#                     setattr(task_in_db, key, value)
#             else:
#                 new_task = models.Task(**task_data, user_id=user.id)
#                 db.add(new_task)

#         db.commit()

#     return {"message": "Google Classroom synced successfully for user"}

@router.get("/classroom/{user_id}/sync")
def sync_user_google_classroom(user_id: int, db: Session = Depends(get_db)):
    # 1️⃣ Get user
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not Found")

    # 2️⃣ Check integration
    user_integration = db.query(models.Integration).filter(
        models.Integration.user_id == user_id,
        models.Integration.service == "google_classroom"
    ).first()
    if not user_integration:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not connected to Google Classroom")

    # 3️⃣ Decrypt access token
    access_token = crypt_utils.decrypt(user_integration.access_token)
    headers = {"Authorization": f"Bearer {access_token}"}

    # 4️⃣ Get courses
    courses_res = requests.get("https://classroom.googleapis.com/v1/courses", headers=headers)
    courses_data = courses_res.json()
    if "error" in courses_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Google API Error: {courses_data['error']['message']}")

    courses = courses_data.get("courses", [])
    if not courses:
        return {"message": "No courses found for this user."}

    tasks_synced = 0

    # 5️⃣ Iterate courses
    for course in courses:
        course_id = course["id"]

        # 6️⃣ Get all coursework for the course
        coursework_res = requests.get(
            f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork",
            headers=headers
        )
        coursework_data = coursework_res.json()
        if "error" in coursework_data:
            print(f"Google Classroom error for course {course_id}: {coursework_data}")
            continue

        coursework_list = coursework_data.get("courseWork", [])

        # 7️⃣ Iterate coursework
        for cw in coursework_list:
            work_id = cw["id"]

            # 8️⃣ Get student's submissions
            submissions_res = requests.get(
                f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork/{work_id}/studentSubmissions?userId=me",
                headers=headers
            )
            submissions_data = submissions_res.json()
            if "error" in submissions_data:
                print(f"Student submission error for coursework {work_id}: {submissions_data}")
                continue

            student_submissions = submissions_data.get("studentSubmissions", [])
            if not student_submissions:
                continue  # student not enrolled or no submission

            # 9️⃣ Parse due date
            if "dueDate" in cw:
                due_date = datetime(
                    cw["dueDate"]["year"],
                    cw["dueDate"]["month"],
                    cw["dueDate"]["day"],
                    cw.get("dueTime", {}).get("hours", 23),
                    cw.get("dueTime", {}).get("minutes", 59),
                    tzinfo=timezone.utc
                )
            else:
                due_date = datetime.now(timezone.utc)

            # 10️⃣ Prepare task
            task_data = {
                "title": cw.get("title", "Untitled"),
                "description": cw.get("description", ""),
                "deadline": due_date,
                "status": "In progress",
                "category": "Classroom",
                "priority": "Medium",
                "source": "Google Classroom",
                "integration_provider_task_id": work_id,
                "updated_at": cw.get("updateTime")
            }

            # 11️⃣ Update or insert task in DB
            task_in_db = db.query(models.Task).filter(
                models.Task.integration_provider_task_id == work_id,
                models.Task.user_id == user.id
            ).first()

            if task_in_db:
                for key, value in task_data.items():
                    setattr(task_in_db, key, value)
            else:
                new_task = models.Task(**task_data, user_id=user.id)
                db.add(new_task)
                tasks_synced += 1

        db.commit()

    return {
        "message": f"Google Classroom synced successfully for userf"
    }
