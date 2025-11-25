from pydantic_settings import BaseSettings
from functools import cached_property

import os

class Settings(BaseSettings):
    backend_base_url: str
    app_sender_email: str 
    sendgrid_api_key: str 
    
    upload_files_directory: str 
    upload_session_expire_minutes: int 
    session_cleanup_refresh_minutes: int 
    
    @cached_property
    def upload_files_dir(self) -> str:
        return self.upload_files_dir if self.upload_files_directory else os.getcwd() + "\\Uploaded_files"

    encryption_key: str 
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int 
    reset_password_token_expire_minutes: int
    email_verification_token_expire_minutes: int
    
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str

    @cached_property
    def database_url(self) -> str:
        """Auto-generate full database URL for SQLAlchemy."""
        return (
            f"postgresql://{self.database_username}:{self.database_password}"
            f"@{self.database_hostname}:{self.database_port}/{self.database_name}")
    
    
    facebook_client_id: str 
    facebook_client_secret: str 
    facebook_redirect_path: str 
    
    def facebook_redirect_uri(self, service: str = "") -> str:
        return f"{self.backend_base_url}{self.facebook_redirect_path}" + (f"/{service}" if service else "")
    
    apple_client_id: str 
    apple_client_secret: str 
    apple_redirect_path: str 
    
    def apple_redirect_uri(self, service: str = "") -> str:
        return f"{self.backend_base_url}{self.apple_redirect_path}" + (f"/{service}" if service else "")
    
    
    google_client_id: str
    google_client_secret: str
    google_gmail_scopes: str 
    google_calendar_scopes: str
    google_tasks_scopes: str
    google_auth_scopes: str 
    google_redirect_path: str
    
    def google_redirect_uri(self, service: str = "") -> str:
        path = f"{self.backend_base_url}{self.google_redirect_path}"
        if service:
            path += f"/{service}"
        return path
    
    zoom_client_id: str 
    zoom_client_secret: str 
    zoom_mettings_scopes: str 
    zoom_redirect_path: str 
    
    def zoom_redirect_uri(self):
        return f"{self.backend_base_url}{self.zoom_redirect_path}"
    




    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"




settings = Settings()


