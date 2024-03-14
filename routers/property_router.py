from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Header
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb, LoanProgress, MortgageInDB
from db.all_db import File
from models.property_models import PropCreate, StatusUpdate
from models.mortgage_models import MortgageCreate
from datetime import datetime, timedelta
from sqlalchemy.orm import joinedload
import jwt
import os
import shutil
import json

utc_now                 = datetime.utcnow()
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

def save_file_to_db(db: Session, entity_type: str, entity_id: int, file_type: str, file_location: str):
    new_file = File(
        entity_type     = entity_type, 
        entity_id       = entity_id, 
        file_type       = file_type, 
        file_location   = file_location)
    db.add(new_file) 
    db.commit()
    db.refresh(new_file)
    return new_file

@router.post("/property/create/", response_model=PropCreate)
async def create_property(
    tax_document    : UploadFile    = FastAPIFile(...), 
    property_photo  : UploadFile    = FastAPIFile(...), 
    property_data   : str           = Form(...),
    db              : Session       = Depends(get_db), 
    token           : str           = Header(None)
):

    property_data = json.loads(property_data)

    if not token:
        log_entry = LogsInDb(action="User Alert", timestamp=datetime.now(), message="Unauthorized property creation attempt (Token not provided)", user_id=None)
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")
    user_id_from_token  = decoded_token.get("id")

    if role_from_token is None:
        log_entry = LogsInDb(
            action      = "User Alert", 
            timestamp   = datetime.now(), 
            message     = "Unauthorized property creation attempt (Invalid or missing role in the token)", 
            user_id     = None)
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "debtor", "agent"]:
        log_entry = LogsInDb(
            action      = "User Alert", 
            timestamp   = datetime.now(), 
            message     = "Unauthorized property creation attempt (Insufficient permissions)", 
            user_id     = None)
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="No tienes permiso para crear propiedades")

    matricula_id    = property_data['matricula_id']
    property_exists = db.query(PropInDB).filter(PropInDB.matricula_id == matricula_id).first()

    if property_exists:
        log_entry = LogsInDb(
            action      = "Property Creation Failed", 
            timestamp   = datetime.now(), 
            message     = f"Property creation failed (Duplicate matricula_id: {matricula_id})", 
            user_id     = user_id_from_token)
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=400, detail="Property with this matricula_id already exists")

    new_property                = PropInDB(**property_data)
    new_property.study          = "study" 
    new_property.comments       = "received"
    
    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    
    new_loan_progress = LoanProgress(
        property_id = new_property.id,
        date        = local_timestamp_str,
        status      = "study",
        user_id     = user_id_from_token,  # Assuming the token contains the user ID initiating the loan progress
        notes       = f"Solicitud de crédito iniciada por {role_from_token}",
        updated_by  = user_id_from_token  
    )
     
    db.add(new_loan_progress)
    db.commit()

    # Uploading files
    upload_folder = './uploads'
    os.makedirs(upload_folder, exist_ok=True)
    
    # Tax document
    tax_document_filename = f"{new_property.id}_tax_{tax_document.filename}"
    tax_document_location = f"{upload_folder}/{tax_document_filename}"
    with open(tax_document_location, "wb") as buffer:
        shutil.copyfileobj(tax_document.file, buffer)
    save_file_to_db(db, "property", new_property.id, "tax_document", tax_document_location)

    # Property photo
    property_photo_filename = f"{new_property.id}_photo_{property_photo.filename}"
    property_photo_location = f"{upload_folder}/{property_photo_filename}"
    with open(property_photo_location, "wb") as buffer:
        shutil.copyfileobj(property_photo.file, buffer)
    save_file_to_db(db, "property", new_property.id, "property_photo", property_photo_location)

    log_entry = LogsInDb(
        action      = "Property Created", 
        timestamp   = datetime.now(), 
        message     = f"Property created with matricula_id: {matricula_id}", 
        user_id     = user_id_from_token
        )
    db.add(log_entry)
    db.commit()

    return {
        "owner_id"      : new_property.owner_id,
        "matricula_id"  : new_property.matricula_id,
        "address"       : new_property.address,
        "neighbourhood" : new_property.neighbourhood,
        "city"          : new_property.city,
        "department"    : new_property.department,
        "strate"        : new_property.strate, 
        "area"          : new_property.area,
        "type"          : new_property.type,
        "tax_valuation" : new_property.tax_valuation,
        "loan_solicited": new_property.loan_solicited,
        "study"         : new_property.study,
        "comments"      : new_property.comments
    }

    
@router.get("/property/retrieve/")
def retrieve_property(id_number: str, db: Session = Depends(get_db)):
    user_properties = []

    user = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    properties = db.query(PropInDB).filter(PropInDB.owner_id == id_number).all()    
    
    if properties:
        for prop in properties:
            user_properties.append(PropCreate(**prop.__dict__))
    else:
        return {"message": "No tienes inmuebles registrados"}
    
    user_mortgages = []
    mortgages = db.query(MortgageInDB).filter(MortgageInDB.debtor_id == id_number).all()

    if mortgages:
        for mort in mortgages:
            mort_dict = {
                "lender_id": mort.lender_id,
                "debtor_id": mort.debtor_id,
                "agent_id": mort.agent_id,
                "matricula_id": mort.matricula_id,
                "initial_balance": mort.initial_balance,
                "interest_rate": mort.interest_rate,
                "mortgage_stage" : mort.mortgage_stage,
                "mortgage_status": mort.mortgage_status,
                "comments"  : mort.comments
            }
            user_mortgages.append(mort_dict)
    else:
        user_mortgages = []  # Keep consistent data structure
    # Log the access
    log_entry = LogsInDb(
        action="Properties component accessed",
        timestamp=local_timestamp_str,
        message=f"Property information accessed by owner",
        user_id=id_number
    )
    db.add(log_entry)
    db.commit()

    return {"properties" : user_properties, "mortgages" : user_mortgages}


@router.get("/properties/{status}")   #LOGS #TOKEN-ROLE # posted, selected, funded, mortgage
def get_properties_by_status(status: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to access properties by status (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token is None:
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to access properties by status (Invalid or missing role in the token)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "lender"]:
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to access properties by status (Insufficient permissions)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para ver propiedades por estado")

    log_entry = LogsInDb(
        action="Properties by Status",
        timestamp=local_timestamp_str,
        message=f"Admin accessed properties with status: {status}",
        user_id=decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    properties_data = []

    properties = (
        db.query(PropInDB)
        .options(joinedload(PropInDB.loan_progress))
        .all()
    )

    for property in properties:
        property_photo = (
            db.query(File)
            .filter_by(entity_type='property', entity_id=property.id, file_type='property_photo')
            .first()
        )

        owner_details = (
            db.query(UserInDB.username, UserInDB.score)
            .filter(UserInDB.id_number == property.owner_id)
            .first()
        )

        # Determine the category of the property based on study and mortgage_stage
        if property.study != 'approved':
            category = "propiedades en estudio"
        elif property.study == 'approved':
            category = "propiedades publicadas"
        for loan_progress in property.loan_progress:
            if loan_progress.mortgage_stage == 'selected':
                category = "propiedades seleccionadas"
                break  # If one loan_progress indicates selected, categorize and stop checking

        properties_data.append({
            "id": property.id,
            "matricula_id": property.matricula_id,
            "address": property.address,
            "neighbourhood": property.neighbourhood,
            "city": property.city,
            "department": property.department,
            "strate": property.strate,
            "area": property.area,
            "type": property.type,
            "tax_valuation": property.tax_valuation,
            "loan_solicited": property.loan_solicited,
            "rate_proposed": property.rate_proposed,
            "evaluation": property.evaluation,
            "prop_status": property.prop_status,
            "prop_study": property.study,
            "comments": property.comments,
            "property_photo": property_photo.file_location if property_photo else None,
            "owner_username": owner_details.username if owner_details else None,
            "owner_score": owner_details.score if owner_details else None,
            "category": category  # Add the determined category
        })

    log_entry = LogsInDb(
        action="Properties by Status Retrieved",
        timestamp=local_timestamp_str,
        message=f"User accessed properties with status: {status}",
        user_id=decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    if not properties_data:
        raise HTTPException(status_code=404, detail="No properties found with the given status")

    return properties_data



@router.get("/admin/properties/")   #LOGS #TOKEN-ROLE # posted, selected, funded, mortgage
def get_properties_by_status(db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to access properties by status (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token is None:
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to access properties by status (Invalid or missing role in the token)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token != "admin":
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to access properties by status (Insufficient permissions)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="No tienes permiso para ver propiedades por estado")

    log_entry = LogsInDb(
        action="Properties accessed by admin",
        timestamp=local_timestamp_str,
        message="Admin accessed properties ALL",
        user_id=decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    properties_data = {
        "propiedades en estudio": [],
        "propiedades publicadas": [],
        "propiedades seleccionadas": []
    }

    properties = db.query(PropInDB).all()

    for property in properties:
        property_photo = db.query(File).filter_by(entity_type='property', entity_id=property.id, file_type='property_photo').first()
        owner_details = db.query(UserInDB.username, UserInDB.score).filter(UserInDB.id_number == property.owner_id).first()
        
        property_dict = {
            "id": property.id,
            "matricula_id": property.matricula_id,
            "address": property.address,
            "neighbourhood": property.neighbourhood,
            "city": property.city,
            "department": property.department,
            "strate": property.strate,
            "area": property.area,
            "type": property.type,
            "tax_valuation": property.tax_valuation,
            "loan_solicited": property.loan_solicited,
            "rate_proposed": property.rate_proposed,
            "evaluation": property.evaluation,
            "prop_status": property.prop_status,
            "prop_study": property.study,
            "comments": property.comments,
            "property_photo": property_photo.file_location if property_photo else None,
            "owner_username": owner_details.username if owner_details else None,
            "owner_score": owner_details.score if owner_details else None
        }

        # Categorizing based on study status and mortgage stage
        if property.study != "approved":
            properties_data["propiedades en estudio"].append(property_dict)
        elif property.study == "approved":
            properties_data["propiedades publicadas"].append(property_dict)
        
        # You will need to adjust this part to correctly query your MortgageInDB based on your database schema
        # For example, if you have a foreign key relationship, you might query like so:
        mortgage_status = db.query(MortgageInDB.mortgage_stage).filter(MortgageInDB.matricula_id == property.matricula_id).first()
        if mortgage_status and mortgage_status.mortgage_stage == "selected":
            properties_data["propiedades seleccionadas"].append(property_dict)

    if not any(properties_data.values()):
        raise HTTPException(status_code=404, detail="No properties found")

    return properties_data



#LOGS #TOKEN-ROLE 
@router.put("/property/update/status/{matricula_id}", response_model=PropCreate)  # posted, selected, funded, mortgage
def update_property_status(matricula_id: str, status_update: StatusUpdate, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized property status update attempt (Token not provided)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit() 
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")

    if role_from_token is None:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized property status update attempt (Invalid or missing role in the token)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized property status update attempt (Insufficient permissions)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para actualizar el estado de la propiedad")

    property = db.query(PropInDB).filter(PropInDB.matricula_id == matricula_id).first()
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Log the status update
    log_entry = LogsInDb(
        action      = "Property Status Updated",
        timestamp   = local_timestamp_str,
        message     = f"Property status updated for matricula_id: {matricula_id} (New Status: {status_update.prop_status})",
        user_id     = decoded_token.get("id")
    )
    db.add(log_entry) 

    property.prop_status = status_update.prop_status  
    db.commit()
    db.refresh(property)

    return PropCreate(**property.__dict__)

@router.put("/property/rate_check/{matricula_id}")  
def update_property_status(matricula_id: str, status_update: StatusUpdate, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt 
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized property status update attempt (Token not provided)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit() 
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")

    if role_from_token is None: 
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized property status update attempt (Invalid or missing role in the token)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token != "debtor":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized property status update attempt (Insufficient permissions)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para actualizar el estado de la propiedad")

    property = db.query(PropInDB).filter(PropInDB.matricula_id == matricula_id).first()
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Log the status update
    log_entry = LogsInDb(
        action      = "Property Status Updated",
        timestamp   = local_timestamp_str,
        message     = f"Property status updated for matricula_id: {matricula_id} (New Status: {status_update.prop_status})",
        user_id     = decoded_token.get("id")
    )
    db.add(log_entry)

    property.prop_status = status_update.prop_status  
    property.comments    = status_update.comments
    property.study       = status_update.study
    
    db.commit()
    db.refresh(property)
    
    #start a mortgage register for tracking the paperwork
    if status_update.study != "canceled":
        # Query for the owner information to get the agent's primary key (PK)
        owner_info = db.query(UserInDB).filter(UserInDB.id_number == property.owner_id).first()
        agent_pk = owner_info.added_by if owner_info else None
        
        # Query for the agent's information using the agent's PK
        agent_info = None
        if agent_pk:
            agent_info = db.query(UserInDB).filter(UserInDB.id == agent_pk).first()
        
        # Creating a provisional Mortgage record
        mortgage = MortgageInDB(
            lender_id       = None,
            debtor_id       = property.owner_id,
            agent_id        = agent_info.id_number if agent_info else None,
            matricula_id    = property.matricula_id,
            initial_balance = 0,  
            interest_rate   = None,  
            mortgage_stage  = "solicited",
            mortgage_status = None,
            comments        = "condiciones aprobadas por el usuario"
        )
        db.add(mortgage)
        db.commit()

    return {
        "message": "Property and possibly mortgage updated successfully",
        "property": {
            "matricula_id": property.matricula_id,
            "prop_status": property.prop_status,
            "comments": property.comments,
            "study": property.study,
        }
    }

@router.put("/property/select/{property_id}")
def select_property(property_id: int, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to select property (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    user_pk = decoded_token.get("pk")
    user_id_from_token = decoded_token.get("id")

    role_from_token = decoded_token.get("role")

    if role_from_token is None or role_from_token != "lender":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized attempt to select property (Invalid role or token)",
            user_id=user_id_from_token
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Unauthorized role or missing token information")

    lender = db.query(UserInDB).filter(UserInDB.id == user_pk).first()
    if not lender:
        raise HTTPException(status_code=404, detail="Lender not found")

    property = db.query(PropInDB).filter(PropInDB.id == property_id).first()
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    property.prop_status = "selected"
    
    #check for the provisional mortgage created when loan was approved
    mortgage = db.query(MortgageInDB).filter(MortgageInDB.matricula_id ==  property.matricula_id).first()
    mortgage.mortgage_stage = "selected"    
    
    loan_progress = LoanProgress(   
        date        = local_timestamp_str,
        property_id = property_id,
        status      = "Tramite de hipoteca solicitado",
        user_id     = lender.id_number,  
        notes       = f"Inversionista {lender.username}",
        updated_by  = user_id_from_token
    )
    db.add(loan_progress)

    # Log the property selection
    log_entry = LogsInDb(
        action="Property Selected",
        timestamp=local_timestamp_str,
        message=f"Property id {property_id} selected by {lender.username}",
        user_id=user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    db.refresh(property)

    return {"message": f"Property with ID {property_id} successfully selected by {lender.username}"}