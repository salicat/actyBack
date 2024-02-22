from typing import Optional
<<<<<<< HEAD
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb
from models.property_models import PropCreate, StatusUpdate
from datetime import datetime, timedelta
import jwt

=======
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Header
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb, LoanProgress
from db.all_db import File
from models.property_models import PropCreate, StatusUpdate
from models.filemodels import FileUpload
from datetime import datetime, timedelta
import jwt
import os
import shutil
import json
>>>>>>> c3c48f9 (Loan Applications update)

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

<<<<<<< HEAD

@router.post("/property/create/", response_model=PropCreate)
def create_property(property_data: PropCreate, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized property creation attempt (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")

    if role_from_token is None:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized property creation attempt (Invalid or missing role in the token)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "debtor"]:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized property creation attempt (Insufficient permissions)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para crear propiedades")

    matricula_id = property_data.matricula_id
    property_exists = db.query(PropInDB).filter(PropInDB.matricula_id == matricula_id).first()

    if property_exists:
        # Log property creation attempt with duplicate matricula_id
        log_entry = LogsInDb(
            action="Property Creation Failed",
            timestamp=local_timestamp_str,
            message=f"Property creation failed (Duplicate matricula_id: {matricula_id})",
            user_id=user_id_from_token
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=400, detail="Property with this matricula_id already exists")

    # Set default property values
    new_property = PropInDB(
        **property_data.dict()
    )
    
    # Set default property values specifically
    new_property.prop_status = "received"
    new_property.comments = "study"

    # Log successful property creation
    log_entry = LogsInDb(
        action="Property Created",
        timestamp=local_timestamp_str,
        message=f"Property created with matricula_id: {matricula_id}",
        user_id=user_id_from_token
    )
    db.add(log_entry)

    db.add(new_property)
    db.commit()
    db.refresh(new_property)

    return PropCreate(**new_property.__dict__)
=======
@router.post("/property/create/", response_model=PropCreate)
async def create_property(
    tax_document: UploadFile = FastAPIFile(...), 
    property_photo: UploadFile = FastAPIFile(...), 
    property_data: str = Form(...),
    db: Session = Depends(get_db), 
    token: str = Header(None)
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
    new_property.prop_status    = "received"
    new_property.comments       = "study"
    
    db.add(new_property)
    db.commit()
    db.refresh(new_property)
    
    new_loan_progress = LoanProgress(
        property_id = new_property.id,
        date        = local_now.date(),
        status      = "study",
        user_id     = user_id_from_token,  # Assuming the token contains the user ID initiating the loan progress
        notes       = "Initial loan progress entry",
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
        "comments"      : new_property.comments
    }

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

    
    

>>>>>>> c3c48f9 (Loan Applications update)



@router.get("/property/retrieve/")
def retrieve_property(id_number: str, db: Session = Depends(get_db)):
    result = []

    user = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    properties = db.query(PropInDB).filter(PropInDB.owner_id == id_number).all()
    
    if properties:
        for prop in properties:
            result.append(PropCreate(**prop.__dict__))
    else:
        return {"message": "No tienes inmuebles registrados"}

    # Log the access
    log_entry = LogsInDb(
        action="Properties component accessed",
        timestamp=local_timestamp_str,
        message=f"Property information accessed by owner",
        user_id=id_number
    )
    db.add(log_entry)
    db.commit()

    return result




<<<<<<< HEAD
@router.get("/properties/{status}")   #LOGS #TOKEN-ROLE
=======
@router.get("/properties/{status}")   #LOGS #TOKEN-ROLE # posted, selected, funded, mortgage
>>>>>>> c3c48f9 (Loan Applications update)
def get_properties_by_status(status: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to access properties by status (Token not provided)",
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
            message     = "Unauthorized attempt to access properties by status (Invalid or missing role in the token)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in  ["admin", "lender"]:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to access properties by status (Insufficient permissions)",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para ver propiedades por estado")

    # Log the successful access by admin
    log_entry = LogsInDb(
        action      = "Properties by Status",
        timestamp   = local_timestamp_str,
        message     = f"Admin accessed properties with status: {status}",
        user_id     = decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    properties = db.query(PropInDB).filter(PropInDB.prop_status == status).all()

    if not properties:
        return []
    return properties


<<<<<<< HEAD
#LOGS #TOKEN-ROLE
=======
#LOGS #TOKEN-ROLE 
>>>>>>> c3c48f9 (Loan Applications update)
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
<<<<<<< HEAD
        db.commit()
=======
        db.commit() 
>>>>>>> c3c48f9 (Loan Applications update)
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

<<<<<<< HEAD





=======
@router.put("/property/rate_check/{matricula_id}", response_model=PropCreate)  # posted, selected, funded, mortgage
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
    db.commit()
    db.refresh(property)

    return PropCreate(**property.__dict__)
>>>>>>> c3c48f9 (Loan Applications update)
