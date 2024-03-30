from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import and_
from db.db_connection import get_db 
from models.penalty_models import PenaltyCreate, CurrentPenalty, PenaltyRequest
from db.all_db import PenaltyInDB, LogsInDb, UserInDB
import os
import jwt

router = APIRouter()

utc_now                 = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def decode_jwt(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Could not decode token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    
@router.get("/logs/{id_number}")
def get_logs(id_number: str, db: Session = Depends(get_db), token: str = Header(None)):
    # Verify if token is provided
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decode the token and handle the case of an invalid token
    try:
        user = decode_jwt(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check if the user has admin role
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to access this resource")

    # Retrieve logs for the specified user
    logs = db.query(LogsInDb).filter(LogsInDb.user_id == id_number).all()
    if not logs:
        return {"message": "No logs found for the specified user"}

    # Prepare the response
    response = []
    for log in logs:
        # Fetch username for each log
        user = db.query(UserInDB).filter(UserInDB.id_number == log.user_id).first()
        username = user.username if user else "Unknown"

        # Format the timestamp
        formatted_date = log.timestamp.strftime("%Y-%m-%d")
        formatted_time = log.timestamp.strftime("%H:%M:%S")

        # Append log information to response
        response.append({
            "action": log.action,
            "message": log.message,
            "username": username,
            "date": formatted_date,
            "time": formatted_time
        })

    return response
