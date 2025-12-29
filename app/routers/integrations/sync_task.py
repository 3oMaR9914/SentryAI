from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.oauth2 import get_current_user
from app.routers.integrations import google_classroom, google_tasks, trello_cards, zoom_meetings

router = APIRouter(prefix="/api/integrations", tags=["Sync User Tasks"])

@router.get("/sync")
async def sync_user(db: Session=Depends(get_db)):
    
    user_id = 1
    user_integrations = db.query(models.Integration).filter(models.Integration.user_id == user_id).all() 
    
    for integration in user_integrations:
        
        match integration.service:
            case "google_tasks":
                google_tasks.sync_user_google_tasks(user_id, db)
                
            case "google_classroom":
                google_classroom.sync_user_google_classroom(user_id, db)
            
            case "trello_cards":
                trello_cards.sync_user_trello_cards(user_id, db)
                
            case "zoom_meetings":
                zoom_meetings.sync_user_zoom_meetings(user_id, db)
                
        
    # user = db.query(models.User).filter(models.User.id == user_id).first()
    # for integration in user_integrations:
        
    #     match integration.service:
    #         case "google_tasks":
    #             google_tasks.sync_user_google_tasks(user, db)
                
    #         case "google_classroom":
    #             google_classroom.sync_user_google_classroom(user, db)
            
    #         case "trello_cards":
    #             trello_cards.sync_user_trello_cards(user, db)
                
    #         case "zoom_meetings":
    #             zoom_meetings.sync_user_zoom_meetings(user, db)
                
    
    return {"message" : "Succefully synced user tasks."}