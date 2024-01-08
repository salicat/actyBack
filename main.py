from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.users_router import router as router_users
from routers.property_router import router as router_properties
from routers.mortgage_router import router as router_mortgages  
from routers.reg_router import router as router_registers
from routers.penalty_router import router as router_penalties
from starlette.middleware.trustedhost import TrustedHostMiddleware

actyval = FastAPI()

actyval.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

origins = [
    "http://localhost.tiangolo.com", 
    "https://localhost.tiangolo.com",
    "http://localhost:8080", 
    "http://127.0.0.1:8000", 
]

actyval.add_middleware(
    CORSMiddleware, 
    allow_origins=origins,
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

actyval.include_router(router_users)
actyval.include_router(router_properties)
actyval.include_router(router_mortgages)
actyval.include_router(router_registers)
actyval.include_router(router_penalties)