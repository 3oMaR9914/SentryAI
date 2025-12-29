from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, date


class UserCreate(BaseModel):
    email: EmailStr
    password: str 
    first_name: str
    last_name: str 
    birthday:  date


class UserRead(BaseModel):
    id: int 
    first_name: str 
    last_name: str  
    birthday: Optional[date] = None # there is a problem here in reading none birthday 
    
    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    title: str 
    category: str       # [Development - Study - Meeting - Assignment - Work - Research - Personal]
    description: Optional[str] = ""
    
    status: str         # [In progress (pending) - Completed - failed]
    priority: str       # [Low - Medium - High]
    deadline: datetime 
    updated_at: Optional[datetime] = None


class TaskRead(BaseModel):
    id: int 
    user_id: int
    
    title: str 
    category: str 
    description: str 
    
    status: str     
    priority: str
    deadline: datetime
    source: str
    
    google_task_id: Optional[str] = None
    google_tasklist_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    id: Optional[str] = None
    