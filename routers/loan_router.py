from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb, LoanProgress, File 
from datetime import datetime, timedelta, timezone
from sqlalchemy.sql import func
import boto3
from botocore.client import Config
from dotenv import load_dotenv
import jwt
import os
import re
 
load_dotenv()

utc_now                 = utc_now = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME = 'actyfiles'

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
    
#file path retrieving:
s3_client = boto3.client(
    's3',
    region_name='us-east-2',  # Ensure this matches your bucket's region
    config=Config(signature_version='s3v4')
) 

AWS_REGION = os.getenv('AWS_REGION', 'us-east-2')  # Default to 'us-east-2' if not set

def generate_presigned_url(bucket_name, object_name, expiration=3600):
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
        return response
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return None


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
        timestamp   = local_timestamp_str, 
        message     = f"Retrieved {len(application_data)} loan applications", 
        user_id     = user_id_from_token)
    db.add(log_entry)
    db.commit()
    
    return application_data



@router.get("/loan_app/detail/{matricula_id}")
async def get_loan_application_details(matricula_id: str, db: Session = Depends(get_db), token: str = Header(None)):
    
    print(f"Processed matricula_id: '{matricula_id}'")  # Debugging output

    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")

    if role_from_token is None or role_from_token not in ["admin", "debtor", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to view loan application details")

    # Normalize input for consistent matching
    normalized_input_matricula_id = ''.join(e for e in matricula_id if e.isalnum() or e in ['-']).lower()

    # Retrieve all properties then filter in Python
    potential_properties = db.query(PropInDB).all()
    property_detail = next((prop for prop in potential_properties if ''.join(e for e in prop.matricula_id if e.isalnum() or e in ['-']).lower() == normalized_input_matricula_id), None)

    if not property_detail:
        raise HTTPException(status_code=404, detail="Property not found")

    # Get loan progress entries
    loan_progress_entries = db.query(LoanProgress).filter(LoanProgress.property_id == property_detail.id).all()
    credit_detail = [{
        "date": entry.date,
        "status": entry.status,
        "notes": entry.notes, 
        "updated_by": entry.updated_by
    } for entry in loan_progress_entries]

    # Debug: Check what we fetch from the database
    print(f"Fetching documents for property_id: {property_detail.id}")
    
    documents = db.query(File).filter(File.entity_type == "property", File.entity_id == property_detail.id).all()
    document_info = [{
        "id": doc.id,
        "file_type": doc.file_type,
        "file_location": generate_presigned_url("actyfiles", doc.file_location) if doc.file_location else "No location found"
    } for doc in documents]

    print(f"Document info: {document_info}")  # Check the output immediately

    # Compile property details
    property_info = {
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
        "study": property_detail.study,
        "comments": property_detail.comments,
        "documents": document_info
    }

    # Fetch owner information
    owner = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()
    owner_info = {
        "user": owner.email,
        "pass": owner.id_number
    } if owner else {}

    return {
        "credit_detail": credit_detail,
        "property_detail": [property_info],
        "owner_info": [owner_info] if owner_info else []
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