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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from smtplib import SMTP
from dotenv import load_dotenv
import jwt
import os
import re
 
load_dotenv()

smtp_host = os.getenv('MAILERTOGO_SMTP_HOST')
smtp_user = os.getenv('MAILERTOGO_SMTP_USER')
smtp_password = os.getenv('MAILERTOGO_SMTP_PASSWORD')
server = SMTP(smtp_host, 587)  
server.starttls() 
server.login(smtp_user, smtp_password) 

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

    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")
    user_id_from_token  = decoded_token.get("id")
    user_pk_from_token  = decoded_token.get("pk")

    if role_from_token is None:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    if role_from_token not in ["admin", "agent", "lawyer"]:
        raise HTTPException(status_code=403, detail="Not authorized to view loan applications")

    applications = []

    if role_from_token == "admin":
        # Si es admin, obtiene todas las solicitudes de crédito y agrupa por property_id,
        # obteniendo solo la más reciente (basada en el id más alto)
        applications = (
            db.query(LoanProgress)
            .order_by(LoanProgress.property_id, LoanProgress.id.desc())
            .all()
        )

        # Crear un diccionario para mantener la solicitud más reciente de cada propiedad
        recent_applications = {}
        for app in applications:
            if app.property_id not in recent_applications:
                recent_applications[app.property_id] = app  # Solo almacenar la primera ocurrencia (la más reciente)
    
        # Aplicar el diccionario a la lista de aplicaciones
        applications = list(recent_applications.values())

    elif role_from_token in ["agent", "lawyer"]:
        # Obtener todos los usuarios añadidos por el agente/abogado
        agent_users = db.query(UserInDB.id_number).filter(UserInDB.added_by == user_pk_from_token).all()
        user_ids = [user.id_number for user in agent_users]

        # Obtener propiedades de esos usuarios
        if user_ids:
            agent_properties = db.query(PropInDB.id).filter(PropInDB.owner_id.in_(user_ids)).all()
            property_ids = [prop.id for prop in agent_properties]

            # Obtener las solicitudes de crédito más recientes para esas propiedades
            if property_ids:
                applications = (
                    db.query(LoanProgress)
                    .filter(LoanProgress.property_id.in_(property_ids))
                    .order_by(LoanProgress.property_id, LoanProgress.id.desc())
                    .all()
                )

                # Crear un diccionario para mantener la solicitud más reciente de cada propiedad
                recent_applications = {}
                for app in applications:
                    if app.property_id not in recent_applications:
                        recent_applications[app.property_id] = app  # Solo almacenar la primera ocurrencia (la más reciente)
                
                # Aplicar el diccionario a la lista de aplicaciones
                applications = list(recent_applications.values())

    if not applications:
        return {"message": "No tienes solicitudes aún"}

    # Preparar los datos para devolver
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
    prop = db.query(PropInDB).filter(PropInDB.id == property_detail.id).first()

    credit_detail = [{
        "date"      : entry.date,
        "status"    : entry.status,
        "notes"     : entry.notes, 
        "evalation" : prop.evaluation,
        "updated_by": entry.updated_by
    } for entry in loan_progress_entries]
    
    documents = db.query(File).filter(File.entity_type == "property", File.entity_id == property_detail.id).all()
    document_info = [{
        "id": doc.id,
        "file_type": doc.file_type,
        "file_location": generate_presigned_url("actyfiles", doc.file_location) if doc.file_location else "No location found"
    } for doc in documents]

    # Compile property details
    property_info = {
        "owner_id"      : property_detail.owner_id,
        "matricula_id"  : property_detail.matricula_id,
        "address"       : property_detail.address,
        "neighbourhood" : property_detail.neighbourhood,
        "city"          : property_detail.city,
        "department"    : property_detail.department,
        "strate"        : property_detail.strate,
        "area"          : property_detail.area,
        "type"          : property_detail.type,
        "tax_valuation" : property_detail.tax_valuation,
        "loan_solicited": property_detail.loan_solicited,
        "study"         : property_detail.study,
        "comments"      : property_detail.comments,
        "observations"  : property_detail.observations,
        "youtube_link"  : property_detail.youtube_link,
        "documents"     : document_info
    }

    # Fetch owner information
    owner = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()
    owner_info = {
        "user": owner.email,
        "pass": owner.id_number
    } if owner else {}

    return {
        "credit_detail"     : credit_detail,
        "property_detail"   : [property_info],
        "owner_info"        : [owner_info] if owner_info else []
    }



@router.post("/loan_progress/update/{matricula_id}")
async def update_loan_application(matricula_id: str, update_data: dict, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decodificación del token
    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")

    # Verificación de autorización
    if role_from_token is None or role_from_token not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to update loan application")

    # Normalización del ID de la matrícula
    normalized_input_matricula_id = ''.join(e for e in matricula_id if e.isalnum() or e in ['-']).lower()
    potential_properties = db.query(PropInDB).all()
    property_detail = next((prop for prop in potential_properties if ''.join(e for e in prop.matricula_id if e.isalnum() or e in ['-']).lower() == normalized_input_matricula_id), None)
    
    # Verificación de existencia de la propiedad
    if not property_detail:
        raise HTTPException(status_code=404, detail="Property not found")

    # Actualización de estado
    status = update_data.get("status", "")
    notes = update_data.get("notes", "")
    score = update_data.get("score", None)
    
    if status:
        if status == "analisis deudor en proceso":
            property_detail.comments = "analysis"
            if score is not None:
                user = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()
                if user:
                    user.score = score  # Actualización del score del usuario
        elif status == "analisis de garantia":
            property_detail.comments = "concept"
        elif status == "Tasa de Interes fijada":
            property_detail.comments = "result"

    # Actualización de tasa propuesta y evaluación
    rate_proposed = update_data.get("rate_proposed")
    if rate_proposed is not None:
        property_detail.rate_proposed = rate_proposed

    evaluation = update_data.get("evaluation")
    if evaluation:
        property_detail.evaluation = evaluation

    # Actualización del estado final de la propiedad (aprobado o rechazado)
    final_status = update_data.get("final_status")
    if final_status == "rejected":
        # Si el estado final es rechazado, actualiza el campo study y comments
        property_detail.study = "rejected"
        # Actualiza el campo comments con "Solicitud negada: " seguido del comentario de evaluación
        property_detail.comments = f"Solicitud negada: {evaluation}" if evaluation else "Solicitud negada: Sin comentarios"

    elif final_status == "approved":
        # Si el estado final es aprobado, simplemente actualiza el campo study
        property_detail.study = "approved"
    
    # Envío de correo electrónico
    owner = db.query(UserInDB).filter(UserInDB.id_number == property_detail.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    owner_email = owner.email
    if final_status:
        if final_status in ["approved", "rejected"]:
            #send email to username with email + temp_password
            sender_email    = "no-reply@mail.app.actyvalores.com" 
            receiver_email  =  owner_email
            subject         = "Hemos Respondido Tu Solicitud"
            body            = "Hemos Respondido Tu Solicitud"
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
                    <h1>Estado de Solicitud de Crédito</h1>
                    <p>Hola {owner.username},</p>
                    <p>Tu solicitud de crédito ha sido decidida. Por favor, visita el sitio para más detalles.</p>
                    <a href='https://app.actyvalores.com'>Ver Detalles</a>
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

    # Registro del progreso del préstamo
    db.add(property_detail)
    new_loan_progress = LoanProgress(
        property_id = property_detail.id, 
        date = local_timestamp_str, 
        status = status, 
        user_id = property_detail.owner_id,
        notes = notes,  
        updated_by = user_id_from_token
    )
    db.add(new_loan_progress)

    # Registro de logs
    log_entry = LogsInDb(
        action = "Loan Application Updated", 
        timestamp = local_timestamp_str, 
        message = f"Updated loan application for matricula_id: {matricula_id} with status: {status}", 
        user_id = user_id_from_token
    )
    db.add(log_entry)

    db.commit()  # Confirma todos los cambios en la base de datos

    return {"message": "Loan application updated successfully"}