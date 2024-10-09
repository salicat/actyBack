from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Header, Body
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import PropInDB, UserInDB, LogsInDb, LoanProgress, MortgageInDB
from db.all_db import File
from models.property_models import PropCreate, StatusUpdate, PropertyUpdate
from models.mortgage_models import MortgageCreate
from datetime import datetime, timedelta, timezone
import boto3
from botocore.config import Config
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from botocore.exceptions import NoCredentialsError
from typing import List
import smtplib
from smtplib import SMTP
import jwt
import os
import shutil
import json


load_dotenv()

smtp_host = os.getenv('MAILERTOGO_SMTP_HOST')
smtp_user = os.getenv('MAILERTOGO_SMTP_USER')
smtp_password = os.getenv('MAILERTOGO_SMTP_PASSWORD')
server = SMTP(smtp_host, 587)  
server.starttls() 
server.login(smtp_user, smtp_password) 


utc_now                 = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

AWS_ACCESS_KEY_ID       = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY   = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME          = 'actyfiles'


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

my_config = Config(
    region_name         = 'us-east-2',  # Change to your bucket's region
    signature_version   = 's3v4'
)

s3_client = boto3.client(
    's3',
    region_name             = 'us-east-2',  # Change to the actual region of your S3 bucket
    config                  = Config(signature_version='s3v4'),
    aws_access_key_id       = AWS_ACCESS_KEY_ID,
    aws_secret_access_key   = AWS_SECRET_ACCESS_KEY
)

#For file saving
def save_file_to_s3_db(db: Session, entity_type: str, entity_id: int, file_type: str, s3_key: str):
    new_file = File(
        entity_type     = entity_type, 
        entity_id       = entity_id, 
        file_type       = file_type, 
        file_location   = s3_key)  # Store the S3 key instead of the local file path
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    return new_file

def upload_file_to_s3(file, bucket_name, object_name):
    try:
        s3_client.upload_fileobj(file, bucket_name, object_name)
        print(f"Upload successful: {object_name}")
        return True
    except Exception as e:
        print(f"Failed to upload {object_name}: {str(e)}")
        return False


#file path retrieving:
def generate_presigned_url(object_name, expiration=3600):
    """Generate a presigned URL to share an S3 object."""
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': S3_BUCKET_NAME,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return None
    return response


@router.post("/property/create/", response_model=PropCreate) 
async def create_property(
    tax_document    : UploadFile                    = FastAPIFile(...), 
    property_photo  : List[UploadFile]              = FastAPIFile(...),
    property_ctl    : UploadFile                    = FastAPIFile(None), 
    apply_form      : UploadFile                    = FastAPIFile(None),  
    additional_docs : Optional[List[UploadFile]]    = FastAPIFile(None),
    property_data   : str                           = Form(...),
    db              : Session                       = Depends(get_db), 
    token           : str                           = Header(None)
):
    try:
        # Load property data from form
        property_data = json.loads(property_data) 

        # Token validation
        if not token:
            raise HTTPException(status_code=401, detail="Token not provided")
        
        decoded_token       = decode_jwt(token) 
        role_from_token     = decoded_token.get("role")
        user_id_from_token  = decoded_token.get("id")
        
        if role_from_token is None or role_from_token not in ["admin", "debtor", "agent"]:
            raise HTTPException(status_code=403, detail="No tienes permiso para crear propiedades")

        if db.query(PropInDB).filter(PropInDB.matricula_id == property_data['matricula_id']).first():
            raise HTTPException(status_code=400, detail="Property with this matricula_id already exists")

        # S3 bucket for file storage
        s3_bucket_name = 'actyfiles'
        file_keys = {}
        files = {
            'tax_document'      : tax_document,
            'property_photo'    : property_photo,
            'property_ctl'      : property_ctl,
            'apply_form'        : apply_form, 
            'additional_docs'   : additional_docs  # Añadimos los documentos adicionales
        }

        # Cargar archivos y recopilar claves
        for file_type, file_list in files.items():
            if isinstance(file_list, list):
                # Si el archivo es una lista (property_photo o additional_docs), manejamos múltiples archivos
                for index, file in enumerate(file_list):
                    if file:  # Asegúrate de que haya archivos antes de procesarlos
                        file_key = f"{property_data['matricula_id']}_{file_type}_{index}_{file.filename}"
                        if not upload_file_to_s3(file.file, s3_bucket_name, file_key):
                            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}")
                        file_keys[f"{file_type}_{index}"] = file_key
            else:
                # Si es un archivo individual
                if file_list:
                    file_key = f"{property_data['matricula_id']}_{file_type}_{file_list.filename}"
                    if not upload_file_to_s3(file_list.file, s3_bucket_name, file_key):
                        raise HTTPException(status_code=500, detail=f"Failed to upload {file_list.filename}")
                    file_keys[file_type] = file_key

        # Create property and loan progress in the database
        new_property = PropInDB(**property_data, study="study", comments="received")
        db.add(new_property)
        db.flush()  # Get new_property.id without committing transaction


        owner_id = property_data['owner_id']
        
        # Save file references in the database
        for file_type, file_key in file_keys.items():
            save_file_to_s3_db(db, "property", new_property.id, file_type, file_key)

        new_loan_progress = LoanProgress(
            property_id = new_property.id,
            date        = local_timestamp_str,
            status      = "study",
            user_id     = owner_id,
            notes       = f"Solicitud de crédito iniciada por {role_from_token}",
            updated_by  = user_id_from_token
        )
        db.add(new_loan_progress)
        db.commit()

        # Enviar correo de notificación
        
        debtor = db.query(UserInDB).filter(UserInDB.id_number == owner_id).first()       
        debtor_email = debtor.email

        # Enviar correo al deudor
        sender_email    = "no-reply@mail.app.actyvalores.com" 
        receiver_email  =  debtor_email
        subject         = "Nueva Solicitud de crédito"
        body            = "Hemos Recibido Tu Solicitud"
        body_html = f"""\
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
                .content {{ background-color: #f4f4f4; padding: 20px; border-radius: 10px; }}
                .footer {{ padding-top: 20px; font-size: 12px; color: #666; }}
                a {{ color: #0073AA; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="content">
                <h1>Nueva Solicitud de Crédito Recibida</h1>
                <p>Hola,</p>
                <p>Hemos recibido tu solicitud de crédito y está siendo procesada. Recibirás una actualización dentro de las próximas 24 horas.</p>
                <p>Gracias por elegirnos!</p>
            </div>
            <div class="footer">
                <p>Saludos,<br>Equipo de Desarrollo<br><a href="https://app.actyvalores.com">actyvalores.com</a></p>
            </div>
        </body>
        </html>
        """

        with smtplib.SMTP(smtp_host, 587) as server:
                server.starttls()
                server.login(smtp_user, smtp_password) 
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = sender_email
                msg['To'] = receiver_email
                part1 = MIMEText(body, 'plain')
                part2 = MIMEText(body_html, 'html')
                msg.attach(part1)
                msg.attach(part2)
                server.sendmail(sender_email, receiver_email, msg.as_string())

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Transaction failed: {str(e)}")

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
                "lender_id"         : mort.lender_id,
                "debtor_id"         : mort.debtor_id,
                "agent_id"          : mort.agent_id,
                "matricula_id"      : mort.matricula_id,
                "initial_balance"   : mort.initial_balance,
                "interest_rate"     : mort.interest_rate,
                "mortgage_stage"    : mort.mortgage_stage,
                "mortgage_status"   : mort.mortgage_status,
                "comments"          : mort.comments
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

        owner_details = db.query(UserInDB.username, UserInDB.score).filter(UserInDB.id_number == property.owner_id).first()

        property_photo = db.query(File).filter_by(entity_type='property', entity_id=property.id, file_type='property_photo').first()
        property_photo_url = generate_presigned_url(property_photo.file_location) if property_photo else None
        
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
            "property_photo": property_photo_url,
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
        property_photo_url = generate_presigned_url(property_photo.file_location) if property_photo else None

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
            "property_photo": property_photo_url  # Use the photo_location variable here
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
        "message": "Property and mortgage updated successfully",
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
    
    #SET THE VALUE FOR THE LENDER TO PAY IN ADVANCE
    advance = max((1.25 / 1000) * property.loan_solicited + (0.035 * property.loan_solicited),1900000)
    
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
    
    
    #send email to username with email + temp_password
    debtor = db.query(UserInDB).filter(UserInDB.id_number == mortgage.debtor_id).first()
    debtor_mail = debtor.email
    lender_mail = lender.email
    
    sender_email    = "no-reply@mail.app.actyvalores.com" 
    receiver_email  =  debtor_mail
    subject         = "Propiedad Seleccionada"
    body            = "Tu Propiedad ha sido seleccionada"
    body_html = f"""\
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
            .content {{ background-color: #f4f4f4; padding: 20px; border-radius: 10px; }}
            .footer {{ padding-top: 20px; font-size: 12px; color: #666; }}
            a {{ color: #0073AA; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="content">
            <h1>Tu Propiedad Ha Sido Seleccionada Para Hipoteca!</h1>
            <p>Hola {debtor.username},</p>
            <p>Vamos a revisar que todo esté en order para continuar con la documentacion.</p>
            <p>En proximos días recibiras instrucciones para acercarte a la notaria a firmar las escrituras</p>
            <br>
            <p>Si tienes alguna duda comunicate con tu asesor, si no tienes uno escribenos a:</p>
            <p>comercial@actyvalores.com</p>
        </div>
        <div class="footer">
            <p>Saludos,<br>Equipo de Desarrollo<br><a href="https://app.actyvalores.com">actyvalores.com</a></p>
        </div>
    </body>
    </html>
    """


    with smtplib.SMTP(smtp_host, 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_password) 
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = receiver_email
            part1 = MIMEText(body, 'plain')
            part2 = MIMEText(body_html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            server.sendmail(sender_email, receiver_email, msg.as_string())
            
    sender_email    = "no-reply@mail.app.actyvalores.com" 
    receiver_email  =  lender_mail
    subject         = "Propiedad Seleccionada"
    body            = "Has Seleccionado Una Propiedad para Invertir"
    body_html = f"""\
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
            .content {{ background-color: #f4f4f4; padding: 20px; border-radius: 10px; }}
            .footer {{ padding-top: 20px; font-size: 12px; color: #666; }}
            a {{ color: #0073AA; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="content">
            <h1>Felicidades!</h1>
            <p>Hola {lender.username},</p>
            <p>Para iniciar el tramite de escrituracion deber seguir los siguientes pasos:</p>
            <p>1. Girar el valor de los tramites notariales equivalentes a: ${advance}</p>
            <p>2. Firmar el contrato de mandato o poder para firma de escrituras en caso de no poder presentarse a la notaria</p>
            <br>
            <p>Datos Bancarios </p>
            <p>
            <br>
            <p>Si tienes alguna duda comunicate con tu asesor, si no tienes uno escribenos a:</p>
            <p>comercial@actyvalores.com</p>
        </div>
        <div class="footer">
            <p>Saludos,<br>Equipo de Desarrollo<br><a href="https://app.actyvalores.com">actyvalores.com</a></p>
        </div>
    </body>
    </html>
    """


    with smtplib.SMTP(smtp_host, 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_password) 
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = receiver_email
            part1 = MIMEText(body, 'plain')
            part2 = MIMEText(body_html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            server.sendmail(sender_email, receiver_email, msg.as_string())
    
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

@router.get("/property_detail/{prop_id}")
def propdetails(prop_id: int, db: Session = Depends(get_db)):
    # Query the property details based on prop_id
    property_detail = db.query(PropInDB).filter(PropInDB.id == prop_id).first()
    if not property_detail:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # Query the owner's details based on the owner_id from property_detail
    owner_detail = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()
    if not owner_detail:
        raise HTTPException(status_code=404, detail="Owner not found")

    loan_details = db.query(LoanProgress).filter(property_detail.id == LoanProgress.property_id).all()[-1]

    # Construct the response dictionary
    property_data = {
        "id"            : property_detail.id,
        "tax_valuation" : property_detail.tax_valuation,
        "rate_proposed" : property_detail.rate_proposed,
        "loan_solicited": property_detail.loan_solicited,
        "estrato"       : property_detail.strate,
        "area"          : property_detail.area,
        "type"          : property_detail.type,
        "city"          : property_detail.city,
        "department"    : property_detail.department,
        "score"         : owner_detail.score,
        "comments"      : loan_details.notes
    }

    return property_data