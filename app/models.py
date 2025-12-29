from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, DateTime, Boolean, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import text 
from datetime import datetime

from app.database import Base 

class User(Base):
    __tablename__ = "users"
    
    # personal data 
    id                      = Column(Integer,                   nullable=False, primary_key=True)
    email                   = Column(String,                    nullable=True, unique=True)
    password                = Column(String,                    nullable=True ) 
    first_name              = Column(String,                    nullable=True ) # same as birthday for nullable
    last_name               = Column(String,                    nullable=True ) # same as birthday for nullable
    birthday                = Column(Date,                      nullable=True ) # fuck apple (apple doesn't provide any personal data)
    created_at              = Column(TIMESTAMP(timezone=True),  nullable=False, server_default=text('now()'))
    
    # App verfications
    refresh_token           = Column(String,                    nullable=True )
    refresh_token_expiry    = Column(DateTime,                  nullable=True ) 
    is_verified             = Column(Boolean,                   nullable=False, default=text('false')) 


class AuthProvider(Base):
    __tablename__ = "auth_providers"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider    = Column(String, nullable=False)  # google / facebook / apple / email
    email       = Column(String, nullable=False) 
    
    owner = relationship("User")


class Integration(Base):
    __tablename__ = "integrations"
    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service         = Column(String)    # google_tasks, google_classroom, zoom_meetings, trello_cards
    # service_id      = Column(String, nullable=True, unique=True)
    
    access_token    = Column(String)
    refresh_token   = Column(String)
    expiry          = Column(DateTime)

    owner = relationship("User")


class Task(Base):
    __tablename__ = "tasks"
    
    id              = Column(Integer,                                               nullable=False, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),   nullable=False)
    source          = Column(String,                                                nullable=False) # google_classroom
    added_at        = Column(TIMESTAMP(timezone=True),                              nullable=False, server_default=text("now()")) 
    updated_at      = Column(TIMESTAMP(timezone=True),                              nullable=True , server_default=text("now()"))
    
    title           = Column(String,                                                nullable=False)
    description     = Column(String,                                                nullable=False, server_default="")
    status          = Column(String,                                                nullable=False)
    deadline        = Column(TIMESTAMP(timezone=True),                              nullable=True)
    
    priority        = Column(String,                                                nullable=False)
    category        = Column(String,                                                nullable=False)
    
    # Integrations sync task id (ALL external IDs in ONE COLUMN)
    integration_provider_task_id = Column(String,                                            nullable=True, unique=True)
    
    owner = relationship("User")



class TempTrelloToken(Base):
    __tablename__ = "temp_trello_tokens"

    id                  = Column(Integer, primary_key=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    oauth_token         = Column(String, nullable=False)
    oauth_token_secret  = Column(String, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)



# class User(Base): 
#     # Apple Integration 
#     apple_email                     = Column(String,    nullable=True, unique=True)
#     apple_id                        = Column(String,    nullable=True, unique=True)
    
#     # Facebook Integration 
#     facebook_email                  = Column(String,    nullable=True, unique=True)
#     facebook_id                     = Column(String,    nullable=True, unique=True)
    
#     # Google integration
#     google_id                       = Column(String,    nullable=True, unique=True)
#     google_email                    = Column(String,    nullable=True, unique=True)
    
    
#     gmail_authorized                = Column(Boolean,   nullable=False, default=text('false')) 
#     gmail_access_token              = Column(String,    nullable=True)
#     gmail_refresh_token             = Column(String,    nullable=True)
#     gmail_token_expiry              = Column(DateTime,  nullable=True)
    
#     google_calendar_authorized      = Column(Boolean,   nullable=False, default=text('false')) 
#     google_calendar_access_token    = Column(String,    nullable=True)
#     google_calendar_refresh_token   = Column(String,    nullable=True)
#     google_calendar_token_expiry    = Column(DateTime,  nullable=True)
    
#     google_tasks_authorized         = Column(Boolean,   nullable=False, default=text('false')) 
#     google_tasks_access_token       = Column(String,    nullable=True)
#     google_tasks_refresh_token      = Column(String,    nullable=True)
#     google_tasks_token_expiry       = Column(DateTime,  nullable=True)
    
#     # zoom integration
#     zoom_authorized                 = Column(Boolean,   nullable=False, default=text('false')) 
#     zoom_access_token               = Column(String,    nullable=True)
#     zoom_refresh_token              = Column(String,    nullable=True)
#     zoom_token_expiry               = Column(DateTime,  nullable=True)


# for gmail emails id storing to prepare it for email tasks extractor llm model

# class Email(Base):
#     __tablename__ = "emails"

#     id          = Column(Integer, primary_key=True, nullable=False)
#     user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
#     gmail_id    = Column(String, nullable=False, unique=True)  # Gmail message ID
#     snippet     = Column(String, nullable=True)
#     subject     = Column(String, nullable=True)
#     from_email  = Column(String, nullable=True)
#     to_email    = Column(String, nullable=True)
#     fetched_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    
#     owner = relationship("User")    


