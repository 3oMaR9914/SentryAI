import socket
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app import models
from app.database import engine 

from app.routers import user, task
from app.routers.auth import app_auth, google_auth, apple_auth, facebook_auth
from app.routers.uploads import upload_files
from app.routers.integrations import google_tasks, zoom_meetings
# from archieve.tester import tester

# creating database if not exists
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

origins = ["*"] # which domains that can acess that api (app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],


)

app.include_router(user.router)
app.include_router(task.router)
app.include_router(app_auth.router)

app.include_router(google_auth.router)
app.include_router(apple_auth.router)
app.include_router(facebook_auth.router)

app.include_router(google_tasks.router)
app.include_router(zoom_meetings.router)

app.include_router(upload_files.router)

# this router for testing urls
# app.include_router(tester.app)




# testing and printing the IP of the server if known
# if __name__ == "__main__":
#     host = "0.0.0.0"
#     port = 8000

#     # Get container/server public IP (if exposed)
#     hostname = socket.gethostname()
#     local_ip = socket.gethostbyname(hostname)

#     print(f"🚀 Server is running locally at: http://127.0.0.1:{port}")
#     print(f"🌍 Server is listening on: http://{local_ip}:{port}")

#     uvicorn.run("main:app", host=host, port=port, reload=True)