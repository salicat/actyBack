from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routers.users_router import router as router_users
from routers.property_router import router as router_properties
from routers.mortgage_router import router as router_mortgages  
from routers.reg_router import router as router_registers
from routers.penalty_router import router as router_penalties
from routers.logs_router import router as router_logs
from routers.loan_router import router as loan_router
from routers.upload_router import router as router_upload 
from routers.file_router import router as router_files
from routers.help_router import router as router_help
from routers.commisions_router import router as router_comissions
from starlette.middleware.trustedhost import TrustedHostMiddleware

actyval = FastAPI()

actyval.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

origins = [
    "http://localhost.tiangolo.com", 
    "https://localhost.tiangolo.com",
    "http://localhost:8080", 
    "http://127.0.0.1:8000", 
    "https://app.actyvalores.com",
    "http://app.actyvalores.com",
    "https://salicat-github-io.vercel.app"
]

actyval.add_middleware(
    CORSMiddleware, 
    allow_origins       = ["*"],
    allow_credentials   = True, 
    allow_methods       = ["*"], 
    allow_headers       = ["*"],
) 

actyval.include_router(router_users)
actyval.include_router(router_properties)
actyval.include_router(router_mortgages)
actyval.include_router(router_registers)
actyval.include_router(router_penalties)
actyval.include_router(router_logs)
actyval.include_router(loan_router)
actyval.include_router(router_upload)
actyval.include_router(router_files)
actyval.include_router(router_help)
actyval.include_router(router_comissions)


# Mount the '/admin/uploads' path to serve static files from the './uploads/' directory
actyval.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


