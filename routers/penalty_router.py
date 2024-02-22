<<<<<<< HEAD
from fastapi import APIRouter, HTTPException, Depends
from datetime import date, timedelta
=======
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from datetime import date, datetime, timedelta
>>>>>>> c3c48f9 (Loan Applications update)
from sqlalchemy.orm import Session
from sqlalchemy import and_
from db.db_connection import get_db 
from models.penalty_models import PenaltyCreate, CurrentPenalty, PenaltyRequest
<<<<<<< HEAD
from db.all_db import PenaltyInDB

router = APIRouter()

=======
from db.all_db import PenaltyInDB, LogsInDb
import os
import jwt

router = APIRouter()

utc_now                 = datetime.utcnow()
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


>>>>>>> c3c48f9 (Loan Applications update)
def last_day_of_month(any_day: date) -> date:
    next_month = any_day.replace(day=28) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day))

@router.post("/create_penalty/", response_model=CurrentPenalty)
<<<<<<< HEAD
async def create_penalty(penalty: PenaltyCreate, db: Session = Depends(get_db)):
=======
async def create_penalty(
    penalty: PenaltyCreate, 
    db: Session = Depends(get_db),
    token: str = Header(None)
):
    # Token and role verification
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    user_id_from_token = decoded_token.get("id")
    user_role = decoded_token.get("role")

    # Check if the user has admin role
    if user_role != 'admin':
        raise HTTPException(status_code=403, detail="Access denied")

>>>>>>> c3c48f9 (Loan Applications update)
    start_date = penalty.month.replace(day=1)
    end_date = last_day_of_month(start_date)

    # Check if a penalty record for this month already exists
    existing_penalty = db.query(PenaltyInDB).filter(
        PenaltyInDB.start_date == start_date, 
        PenaltyInDB.end_date == end_date
    ).first()

    if existing_penalty:
        raise HTTPException(status_code=400, detail="Penalty for this month already exists")

    # Create new penalty interest record
    db_penalty = PenaltyInDB(
        start_date=start_date,
        end_date=end_date,
        penalty_rate=penalty.penalty_rate
    )
    
    db.add(db_penalty)
    db.commit()
    db.refresh(db_penalty)
<<<<<<< HEAD
    
=======

    log_entry = LogsInDb(
        action      = "Created Penalty Rate",
        timestamp   = local_timestamp_str,
        message     = f"Admin created a new penalty rate for {start_date.strftime('%Y-%m')}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

>>>>>>> c3c48f9 (Loan Applications update)
    return CurrentPenalty(
        start_date=db_penalty.start_date,
        end_date=db_penalty.end_date,
        penalty_rate=db_penalty.penalty_rate
    )

<<<<<<< HEAD
@router.get("/get_current_penalty/{month}/{year}", response_model=CurrentPenalty)
=======
@router.get("/get_penalty_rates/")
async def get_penalty_rates(db: Session = Depends(get_db), token: str = Header(None)):
    # Token and role verification
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    user_id_from_token = decoded_token.get("id")
    user_role = decoded_token.get("role")

    # Check if the user has admin role
    if user_role != 'admin':
        raise HTTPException(status_code=403, detail="Access denied")

    # Get the current date and calculate the start of the current month
    current_date = datetime.now()
    start_of_current_month = current_date.replace(day=1)

    # Query the last 6 months of penalty rates
    penalty_rates = db.query(PenaltyInDB).filter(
        PenaltyInDB.start_date >= (start_of_current_month - timedelta(days=182))
    ).order_by(PenaltyInDB.start_date).all()

    # Prepare the response
    response = {}
    for month_back in range(5, -1, -1):
        # Calculate the start of the month
        month_date = (start_of_current_month - timedelta(days=month_back * 30)).replace(day=1)
        month_str = month_date.strftime("%Y-%m")

        # Find the penalty rate for the specific month
        rate = next((rate for rate in penalty_rates if rate.start_date.month == month_date.month and rate.start_date.year == month_date.year), None)
        response[month_str] = rate.penalty_rate if rate else "no definido"

    # Log the access to penalty rates
    log_entry = LogsInDb(
        action      = "Accessed Penalty Rates",
        message     = "Admin accessed the last 6 months of penalty rates",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    return response



@router.get("/get_current_penalty/{month}/{year}")
>>>>>>> c3c48f9 (Loan Applications update)
async def get_current_penalty(month: int, year: int, db: Session = Depends(get_db)):
    month_start = date(year, month, 1)
    month_end = last_day_of_month(month_start)

    penalty = db.query(PenaltyInDB).filter(
        and_(PenaltyInDB.start_date == month_start, PenaltyInDB.end_date == month_end)
    ).first()

    if not penalty:
<<<<<<< HEAD
        raise HTTPException(status_code=404, detail="Penalty for this month not found")

    return CurrentPenalty(
        start_date  = penalty.start_date,
        end_date    = penalty.end_date,
        penalty_rate= penalty.penalty_rate
    )
=======
        return { "message": "No hay intereses de mora para este mes"}

    return penalty 

>>>>>>> c3c48f9 (Loan Applications update)
