from fastapi import APIRouter, UploadFile, File, HTTPException, Depends 
from fastapi_utils.tasks import repeat_every

from app.routers.uploads.session_system import SessionSystem
from app import models, oauth2
from app.config import settings 

router = APIRouter(
    prefix="/api/uploads",
    tags=["Uploads"],
    )

UPLOAD_FILES_DIR = settings.upload_files_dir
UPLOAD_SESSION_EXPIRE_MINUTES = settings.upload_session_expire_minutes

session_sys = SessionSystem(UPLOAD_FILES_DIR, UPLOAD_SESSION_EXPIRE_MINUTES)

@router.post("/")
async def upload(file: UploadFile = File(...), current_user: models.User = Depends(oauth2.get_current_user)):
    return session_sys.create_session(file, current_user)

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, current_user: models.User = Depends(oauth2.get_current_user)):
    session = session_sys.get_session(session_id, current_user)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    session_sys.delete_session(session_id)
    return {"detail": "Session deleted"}


@router.on_event("startup")
@repeat_every(seconds=settings.session_cleanup_refresh_seconds)  
async def auto_cleanup_sessions():
    expired = await session_sys.cleanup_expired_sessions()
    if expired:
        print(f"Deleted expired sessions: {expired}")