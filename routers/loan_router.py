from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb, LoanProgress, File 
from models.property_models import PropCreate, StatusUpdate
from models.loan_prog_models import LoanProgressInfo, LoanProgressUpdate
from datetime import datetime, timedelta, timezone
from sqlalchemy.sql import func
import jwt
import re
 

utc_now                 = utc_now = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()

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
    


@router.get("/loan_progress/applications/")
async def get_loan_applications(db: Session = Depends(get_db), token: str = Header(None)):
    
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")
    user_pk_from_token = decoded_token.get("pk")

    if role_from_token is None:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to view loan applications")

    applications = []

    if role_from_token == "admin":
        # Existing logic for admins to retrieve all applications
        subquery = (
            db.query(
                LoanProgress.property_id, 
                func.max(LoanProgress.id).label("max_id")
            )
            .group_by(LoanProgress.property_id)
            .subquery()
        )

        applications = (
            db.query(LoanProgress)
            .join(subquery, LoanProgress.id == subquery.c.max_id)
            .all()
        )
    
    elif role_from_token == "agent":
        # Modified logic for agents to retrieve applications for their users
        subquery = ( 
            db.query(
                LoanProgress.property_id, 
                func.max(LoanProgress.id).label("max_id")
            )
            .join(PropInDB, PropInDB.id == LoanProgress.property_id)
            .join(UserInDB, UserInDB.id_number == PropInDB.owner_id)
            .filter(UserInDB.added_by == user_pk_from_token)
            .group_by(LoanProgress.property_id)
            .subquery()
        )

        applications = (
            db.query(LoanProgress)
            .join(subquery, LoanProgress.id == subquery.c.max_id)
            .all()
        )

    if not applications:
        return {"message" : "No Tienes Solicitudes Aún"}
    
    application_data = []
    for app in applications:
        property_info = db.query(PropInDB).filter(PropInDB.id == app.property_id).first()
        if property_info:
            owner_info = db.query(UserInDB).filter(UserInDB.id_number == property_info.owner_id).first()
            application_data.append({
                "matricula_id"  : property_info.matricula_id,
                "owner_id"      : property_info.owner_id,
                "owner_username": owner_info.username if owner_info else None,
                "status"        : app.status,
                "last_date"     : app.date,
                "notes"         : app.notes
            })

    # Log the action after successful retrieval
    action_description = "Loan Applications Retrieved by Admin" if role_from_token == "admin" else "Loan Applications Retrieved by Agent"
    log_entry = LogsInDb(
        action      = action_description, 
        timestamp   = datetime.now(), 
        message     = f"Retrieved {len(application_data)} loan applications", 
        user_id     = user_id_from_token)
    db.add(log_entry)
    db.commit()
    
    return application_data



@router.get("/loan_app/detail/{matricula_id}")
async def get_loan_application_details(matricula_id: str, db: Session = Depends(get_db), token: str = Header(None)):
    
    print(f"Processed matricula_id: '{matricula_id}'")

    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")

    if role_from_token is None:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "debtor", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to view loan application details")

    normalized_input_matricula_id = ''.join(e for e in matricula_id if e.isalnum() or e in ['-']).lower()

    # Retrieve all properties then filter in Python (Consider optimizing based on your actual dataset size and indexing)
    potential_properties = db.query(PropInDB).all()
    property_detail = next((prop for prop in potential_properties if ''.join(e for e in prop.matricula_id if e.isalnum() or e in ['-']).lower() == normalized_input_matricula_id), None)
    if not property_detail:
        raise HTTPException(status_code=404, detail="Property not found")

    loan_progress_entries = db.query(LoanProgress).filter(LoanProgress.property_id == property_detail.id).all()

    credit_detail = []

    for entry in loan_progress_entries:
        credit_detail.append({
            "date": entry.date,
            "status": entry.status,
            "notes": entry.notes, 
            "updated_by": entry.updated_by
        })
        
    documents = (
                db.query(File)
                .filter(File.entity_type == "property", File.entity_id == property_detail.id)
                .all()
            )

    property_info = []

    property_info.append({
        "owner_id": property_detail.owner_id,
        "matricula_id": property_detail.matricula_id,
        "address": property_detail.address,
        "neighbourhood": property_detail.neighbourhood,
        "city": property_detail.city,
        "department": property_detail.department,
        "strate": property_detail.strate,
        "area": property_detail.area,
        "type": property_detail.type,
        "tax_valuation": property_detail.tax_valuation,
        "loan_solicited": property_detail.loan_solicited,
        "rate_proposed": property_detail.rate_proposed,
        "evaluation": property_detail.evaluation,
        "prop_status": property_detail.prop_status,
        "comments": property_detail.comments,
        "documents"     : [
                    {
                        "id"            : doc.id,
                        "file_type"     : doc.file_type,
                        "file_location" : doc.file_location 
                    }
                    for doc in documents
                ]
    })
    user_credentials = []
    owner = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()

    if owner:
        user_credentials.append({
            "user"  : owner.email,
            "pass"  : owner.id_number
        })


    # Log the action after successful retrieval
    log_entry = LogsInDb(action="Loan Application Detail Retrieved", timestamp=datetime.now(), message=f"Retrieved loan application details for matricula_id: {matricula_id}", user_id=user_id_from_token)
    db.add(log_entry)
    db.commit()

    return {
        "credit_detail": credit_detail,
        "property_detail": property_info,
        "owner_info" : user_credentials
    }



@router.post("/loan_progress/update/{matricula_id}")
async def update_loan_application(matricula_id: str, update_data: dict, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")

    if role_from_token is None or role_from_token not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to update loan application")

    normalized_input_matricula_id = ''.join(e for e in matricula_id if e.isalnum() or e in ['-']).lower()
    potential_properties = db.query(PropInDB).all()
    property_detail = next((prop for prop in potential_properties if ''.join(e for e in prop.matricula_id if e.isalnum() or e in ['-']).lower() == normalized_input_matricula_id), None)
    if not property_detail:
        raise HTTPException(status_code=404, detail="Property not found")

    status = update_data.get("status", "")
    notes = update_data.get("notes", "")
    score = update_data.get("score", None)
    
    if status:
        if status == "analisis deudor en proceso":
            property_detail.comments = "analysis"
            if score is not None:
                # Ensure we're looking up the user based on id_number as mentioned
                user = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()
                if user:
                    user.score = score  # Update the user's score
        elif status == "analisis de garantia":
            property_detail.comments = "concept"
        elif status == "Tasa de Interes fijada":
            property_detail.comments = "result"

    rate_proposed = update_data.get("rate_proposed")
    if rate_proposed is not None:
        property_detail.rate_proposed = rate_proposed

    evaluation = update_data.get("evaluation")
    if evaluation:
        property_detail.evaluation = evaluation

    final_status = update_data.get("final_status")
    if final_status:
        if final_status == "approved":
            property_detail.study = "approved"
        elif final_status == "rejected":
            property_detail.study = "rejected"

    db.add(property_detail)

    new_loan_progress = LoanProgress(
        property_id=property_detail.id, 
        date=datetime.now(), 
        status=status, 
        user_id=property_detail.owner_id,
        notes=notes,  
        updated_by=user_id_from_token
    )
    db.add(new_loan_progress)

    log_entry = LogsInDb(
        action="Loan Application Updated", 
        timestamp=datetime.now(), 
        message=f"Updated loan application for matricula_id: {matricula_id} with status: {status}", 
        user_id=user_id_from_token
    )
    db.add(log_entry)

    db.commit()  # This should commit all changes including the user score update.

    return {"message": "Loan application updated successfully"}