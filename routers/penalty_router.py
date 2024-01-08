from fastapi import APIRouter, HTTPException, Depends
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from db.db_connection import get_db 
from models.penalty_models import PenaltyCreate, CurrentPenalty, PenaltyRequest
from db.all_db import PenaltyInDB

router = APIRouter()

def last_day_of_month(any_day: date) -> date:
    next_month = any_day.replace(day=28) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day))

@router.post("/create_penalty/", response_model=CurrentPenalty)
async def create_penalty(penalty: PenaltyCreate, db: Session = Depends(get_db)):
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
    
    return CurrentPenalty(
        start_date=db_penalty.start_date,
        end_date=db_penalty.end_date,
        penalty_rate=db_penalty.penalty_rate
    )

@router.get("/get_current_penalty/{month}/{year}", response_model=CurrentPenalty)
async def get_current_penalty(month: int, year: int, db: Session = Depends(get_db)):
    month_start = date(year, month, 1)
    month_end = last_day_of_month(month_start)

    penalty = db.query(PenaltyInDB).filter(
        and_(PenaltyInDB.start_date == month_start, PenaltyInDB.end_date == month_end)
    ).first()

    if not penalty:
        raise HTTPException(status_code=404, detail="Penalty for this month not found")

    return CurrentPenalty(
        start_date  = penalty.start_date,
        end_date    = penalty.end_date,
        penalty_rate= penalty.penalty_rate
    )