from fastapi import APIRouter, status, HTTPException, Response, Depends 
from sqlalchemy.orm import Session 
from typing import List 

from app.database import get_db 
from app import schemas, models, oauth2


router = APIRouter(
    prefix="/api/tasks",
    tags = ["Tasks"]
)


# require authentication (login)
@router.post("/", response_model=schemas.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(task: schemas.TaskCreate, db: Session=Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    
    task = models.Task(**task.dict(), user_id=current_user.id, source="sentry")

    db.add(task)
    db.commit()
    db.refresh(task)
    
    return task 


# require authentication (login)
@router.get("/", response_model=List[schemas.TaskRead], status_code=status.HTTP_200_OK)
def get_user_tasks(db: Session=Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):

    tasks = db.query(models.Task).filter(models.Task.user_id == current_user.id).all()

    return tasks 


# require authentication (login)
@router.get("/{task_id}", response_model=schemas.TaskRead, status_code=status.HTTP_200_OK)
def get_task(task_id: int, db: Session=Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    
    task = db.query(models.Task).filter(models.Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"task with id: {task_id} is not exist")
    
    if current_user.id != task.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")

    return task 


# require authentication (login)
@router.put("/{task_id}", response_model=schemas.TaskRead, status_code=status.HTTP_200_OK)
def edit_task(task_id: int, updated_task: schemas.TaskCreate, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):

    task_query = db.query(models.Task).filter(models.Task.id == task_id)
    task = task_query.first()
    
    if task == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"task with id: {task_id} is not exist")
    
    if task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")
    
    task_query.update(updated_task.dict(), synchronize_session=False)
    db.commit()
    
    return task_query.first()


# require authentication (login)
@router.delete("/{task_id}", response_model=schemas.TaskRead)
def remove_task(task_id, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    
    task_query = db.query(models.Task).filter(models.Task.id == task_id)
    task = task_query.first()
    
    if task == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"task with id: {task_id} is not exist")
    
    if task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")
    
    task_query.delete(synchronize_session=False)
    db.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


