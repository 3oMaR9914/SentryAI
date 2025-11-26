import os
import time
import uuid
import shutil
import asyncio
from fastapi import HTTPException, status, UploadFile

from app import models  
from app.config import settings 

class SessionSystem:
    def __init__(self, upload_dir="uploads", session_timeout_minutes=30):
        self.upload_dir = upload_dir
        self.session_timeout_minutes = session_timeout_minutes
        self.sessions = {}
        os.makedirs(self.upload_dir, exist_ok=True)


    async def create_session(self, file: UploadFile, user: models.User):
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        
        if file is None or file.filename == "": 
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File doesn't uploaded correctly.")
        
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(self.upload_dir, session_id)
        os.makedirs(session_folder, exist_ok=True)

        file_path = os.path.join(session_folder, file.filename)
        
        contents = await file.read() 
        if not contents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

        with open(file_path, "wb") as f:
            f.write(contents)

        self.sessions[session_id] = {
            "id": session_id,
            "user_id": user.id,
            "file_path": file_path,
            "created_at": time.time(),
        }

        return {
            "session_id": session_id,
            "user_id": user.id,
            "file_path": file_path
        }


    def get_session(self, session_id, user: models.User):

        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        session = self.sessions.get(session_id)
        if not session or session["user_id"] != user.id:
            raise HTTPException(status_code=403, detail="Session not found or not owned by user")

        if time.time() - session["created_at"] > self.session_timeout_minutes :
            self.delete_session(session_id)
            raise HTTPException(status_code=410, detail="Session expired")

        return session

    def delete_session(self, session_id):
        session_folder = os.path.join(self.upload_dir, session_id)
        
        if os.path.exists(session_folder):
            shutil.rmtree(session_folder)
            
        if session_id in self.sessions:
            del self.sessions[session_id]

    async def cleanup_expired_sessions(self):
        while True:
            now = time.time()
            expired = [
                sid for sid, s in self.sessions.items()
                if now - s["created_at"] > self.session_timeout_minutes * 60
            ]
            
            for sid in expired:
                self.delete_session(sid)
            await asyncio.sleep(settings.session_cleanup_refresh_minutes)
