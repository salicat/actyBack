from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Header, Body
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb, LoanProgress, MortgageInDB
from db.all_db import File
from models.property_models import PropCreate, StatusUpdate, PropertyUpdate
from models.mortgage_models import MortgageCreate
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import joinedload
import jwt
import os
import shutil
import json

utc_now                 = datetime.now(timezone.utc)
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
    property_ctl    : UploadFile    = FastAPIFile(...), 
    app_form        : Optional[UploadFile] = FastAPIFile(None),
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
            timestamp   = local_timestamp_str, 
            message     = "Unauthorized property creation attempt (Invalid or missing role in the token)", 
            user_id     = None)
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "debtor", "agent"]:
        log_entry = LogsInDb(
            action      = "User Alert", 
            timestamp   = local_timestamp_str, 
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
            timestamp   = local_timestamp_str, 
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

    # Property CTL
    property_ctl_filename = f"{new_property.id}_ctl_{property_ctl.filename}"
    property_ctl_location = f"{upload_folder}/{property_ctl_filename}"
    with open(property_ctl_location, "wb") as buffer:
        shutil.copyfileobj(property_ctl.file, buffer)
    save_file_to_db(db, "property", new_property.id, "property_ctl", property_ctl_location)
    
    #application_form
    if app_form:    
        app_form_filename   = f"{new_property.id}_appForm_{app_form.filename}"
        app_form_location   =f"{upload_folder}/{app_form_filename}"
        with open(app_form_location, "wb") as buffer:
            shutil.copyfileobj(app_form.file, buffer)
        save_file_to_db(db, "property", new_property.id, "app_form", app_form_location)
        
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

    return {"properties" : user_properties, "mortgages" : user_mortgages}


@router.get("/properties/{status}")  # LOGS #TOKEN-ROLE # posted, selected, funded, mortgage
def get_properties_by_status(status: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token is None:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "lender"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver propiedades por estado")

    properties_data = []
    processed_property_ids = set()  # To track properties already added

    # Handling different statuses without making new imports
    if status == 'analysis':
        query_status = 'study' if status == 'analysis' else 'approved'
        properties = db.query(PropInDB).filter(PropInDB.study == query_status).all()
    if status == 'available':
        properties = db.query(PropInDB).filter(PropInDB.prop_status == 'available', PropInDB.comments == 'approved').all()
    elif status in ['selected', 'loaned']:
        property_ids = {mort.matricula_id for mort in db.query(MortgageInDB).filter(MortgageInDB.mortgage_stage == status).all()}
        properties = db.query(PropInDB).filter(PropInDB.matricula_id.in_(property_ids)).all()
    else:
        raise HTTPException(status_code=400, detail="Invalid status provided")

    for property in properties:
        if property.matricula_id in processed_property_ids:
            continue  # Skip this property as it has already been processed

        property_photo = db.query(File).filter_by(entity_type='property', entity_id=property.id, file_type='property_photo').first()
        owner_details = db.query(UserInDB.username, UserInDB.score).filter(UserInDB.id_number == property.owner_id).first()

        property_data = {
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

        properties_data.append(property_data)
        processed_property_ids.add(property.matricula_id)  # Mark this property as processed

    if not properties_data:
        return {"message" : "No hay Activos Disponibles"}

    return properties_data

#PUBLIC ENDOPOINT

@router.get("/public-properties/{referralId}")
def get_properties_by_referral(referralId: str, db: Session = Depends(get_db)):

    properties = db.query(PropInDB).filter(
        PropInDB.prop_status == 'available',
        PropInDB.comments == 'approved'
    ).all()
    
    properties_data = []
    for property in properties:
        property_photo = db.query(File).filter_by(
            entity_type='property',
            entity_id=property.id,
            file_type='property_photo'
        ).first()

        # Ensure that property_photo is not None before accessing its attributes
        photo_location = property_photo.file_location if property_photo else None

        properties_data.append({
            "id": property.id,
            "address": property.address,
            "city": property.city,
            "department": property.department,
            "area": property.area,
            "type": property.type,
            "tax_valuation": property.tax_valuation,
            "loan_solicited": property.loan_solicited,
            "rate_proposed": property.rate_proposed,
            "prop_status": property.prop_status,
            "comments": property.comments,
            "property_photo": photo_location  # Use the photo_location variable here
        })

    if not properties_data:
        return {"message": "No properties available for this referral"}

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
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to access properties by status (Insufficient permissions)",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="No tienes permiso para ver propiedades por estado")

    properties_data = {
        "estudio"       : [],
        "publicadas"    : [],
        "seleccionadas" : []
    }

    selected_property_ids = set()
    mortgages = db.query(MortgageInDB).all()
    for mort in mortgages:
        if mort.mortgage_stage == "selected":
            selected_property_ids.add(mort.matricula_id)

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

        if property.matricula_id in selected_property_ids:
            property_dict["stage"] = "selected"
            properties_data["seleccionadas"].append(property_dict)
            continue  # Skip adding this property to other categories

        # Categorizing based on study status and mortgage stage
        if property.study != "approved":
            properties_data["estudio"].append(property_dict)
        elif property.study == "approved":
            properties_data["publicadas"].append(property_dict)

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
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to select property (Token not provided)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    user_pk             = decoded_token.get("pk")
    user_id_from_token  = decoded_token.get("id")

    role_from_token = decoded_token.get("role")

    if role_from_token is None or role_from_token != "lender":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to select property (Invalid role or token)",
            user_id     = user_id_from_token
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
    
    # Check for the provisional mortgage created when loan was approved
    mortgage = db.query(MortgageInDB).filter(MortgageInDB.matricula_id == property.matricula_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="Provisional mortgage not found")
    
    # Update the mortgage provisional register
    mortgage.lender_id          = lender.id_number
    mortgage.mortgage_stage     = "selected"
    mortgage.initial_balance    = 0
    mortgage.interest_rate      = property.rate_proposed
    mortgage.mortgage_status    = "solicited"
    mortgage.comments           = "...in process"
    
    db.add(mortgage)
    db.commit()

    property.comments = "selected"
    
    # Log the property selection
    log_entry = LogsInDb(
        action      = "Property Selected",
        timestamp   = local_timestamp_str,
        message     = f"Property id {property_id} selected by {lender.username}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    return {"message": f"Property with ID {property_id} successfully selected by {lender.username}"}

@router.put("/complete_property/{prop_matricula_id}")
def update_prop(prop_matricula_id: str, update_data: PropertyUpdate, db: Session = Depends(get_db), token: str = Header(None)):
    # Decode the token to validate the user
    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token is None or role_from_token != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized role or missing token information")

    property = db.query(PropInDB).filter(PropInDB.matricula_id == prop_matricula_id).first()
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Explicitly update each field if provided
    if update_data.address is not None:
        property.address = update_data.address
    if update_data.neighbourhood is not None:
        property.neighbourhood = update_data.neighbourhood
    if update_data.city is not None:
        property.city = update_data.city
    if update_data.department is not None:
        property.department = update_data.department
    if update_data.strate is not None:
        property.strate = update_data.strate
    if update_data.area is not None:
        property.area = update_data.area
    if update_data.type is not None:
        property.type = update_data.type
    if update_data.tax_valuation is not None:
        property.tax_valuation = update_data.tax_valuation
    if update_data.loan_solicited is not None:
        property.loan_solicited = update_data.loan_solicited

    db.commit()
    return {"message": "Property updated successfully"}