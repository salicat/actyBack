from fastapi import Depends, APIRouter, HTTPException, Header, UploadFile, File as FastAPIFile, Form
from sqlalchemy.orm import Session 
from db.db_connection import get_db
from db.all_db import UserInDB, MortgageInDB, LogsInDb, RegsInDb, PropInDB, PenaltyInDB, File
from models.user_models import UserIn, UserAuth, UserInfoAsk, PasswordChange
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
import smtplib
from smtplib import SMTP
from dotenv import load_dotenv 
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import boto3
from botocore.config import Config
import json 
import os
import random
import string
import secrets 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

utc_now                 = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

load_dotenv()

smtp_host = os.getenv('MAILERTOGO_SMTP_HOST')
smtp_user = os.getenv('MAILERTOGO_SMTP_USER')
smtp_password = os.getenv('MAILERTOGO_SMTP_PASSWORD')
# server = SMTP(smtp_host, 587)  
# server.starttls() 
# server.login(smtp_user, smtp_password) 

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET_NAME = 'actyfiles'

my_config = Config(
    region_name='us-east-2',  # Change to your bucket's region
    signature_version='s3v4'
)

s3_client = boto3.client(
    's3',
    region_name='us-east-2',  # Change to the actual region of your S3 bucket
    config=Config(signature_version='s3v4'),
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

def save_file_to_s3_db(db: Session, entity_type: str, entity_id: int, file_type: str, s3_key: str):
    new_file = File(
        entity_type = entity_type, 
        entity_id = entity_id, 
        file_type = file_type, 
        file_location = s3_key)  # Store the S3 key instead of the local file path
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

router = APIRouter()

def save_file_to_db(db: Session, entity_type: str, entity_id: int, file_type: str, file_location: str):
    new_file = File(
        entity_type=entity_type,
        entity_id=entity_id,
        file_type=file_type,
        file_location=file_location)
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    return new_file

required_fields_by_role = {
    "agent"     : ["username", 
                   "id_number", 
                   "phone",
                   "user_city", 
                   "user_department", 
                   "tax_id",
                   "account_type",
                   "account_number",
                   "bank_name"
                   ], 
    "lawyer"     : ["username", 
                   "id_number", 
                   "phone",
                   "user_city", 
                   "user_department", 
                   "tax_id",
                   "account_type",
                   "account_number",
                   "bank_name"
                   ], 
    "lender"    : ["username", 
                   "id_number",
                   "phone", 
                   "user_city", 
                   "user_department", 
                   "tax_id",
                   "account_type",
                   "account_number",
                   "bank_name"
                   ], 
    "debtor"    : ["username", 
                   "id_number", 
                   "phone", 
                   "legal_address",
                   "user_city", 
                   "user_department", 
                   "tax_id"
                   ],
    "admin"     : []
}

def validate_user_info(user: UserInDB) -> bool:
    required_fields = required_fields_by_role.get(user.role, [])
    user_data = user.__dict__ 
    for field in required_fields:
        if field not in user_data or not user_data[field]:
            return False
    return True

def create_temp_password(username):
    part_username = username[:3]  
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return part_username + random_part

@router.post("/user/create/")  # LOGS
async def create_user(user_in: UserIn, db: Session = Depends(get_db)):
    allowed_roles = ["admin", "lender", "debtor", "agent", "lawyer"]  
    
    if user_in.role.lower() not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role. Allowed roles are: admin, lender, debtor, agent")

    existing_user = db.query(UserInDB).filter(UserInDB.username == user_in.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Usuario ya esta en uso")
    
    existing_user = db.query(UserInDB).filter(UserInDB.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email ya esta en uso")

    existing_user = db.query(UserInDB).filter(UserInDB.phone == user_in.phone).first()
    if existing_user:
        print("Test query found the user:", existing_user.id_number)
        raise HTTPException(status_code=400, detail="Nro telefonico ya fue registrado")
    
    existing_user = db.query(UserInDB).filter(UserInDB.id_number == user_in.id_number).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Ya hay un usuario credo con ese ID")

    hashed_password = None
    if user_in.hashed_password:
        hashed_password = pwd_context.hash(user_in.hashed_password)
    
    new_user = UserInDB(
        role            = user_in.role,
        username        = user_in.username,
        email           = user_in.email,
        hashed_password = hashed_password,
        phone           = user_in.phone,
        legal_address   = user_in.legal_address if user_in.legal_address is not None else "",
        user_city       = user_in.user_city if user_in.user_city is not None else "",  # Ensure user_city is not None
        user_department = user_in.user_department,
        id_number       = user_in.id_number
    )
    
    if user_in.agent is not None:
        new_user.agent = user_in.agent
    
    new_user.user_status = "incomplete"  # FIX APPLIED ON AGENTS
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_entry = LogsInDb(
        action      = "User Created",
        timestamp   = local_timestamp_str,
        message     = f"User with username '{user_in.username}' has been registered",
        user_id     = new_user.id_number
    )
    db.add(log_entry)
    db.commit()

    user_data = {
        "id"                : new_user.id,
        "role"              : new_user.role,
        "username"          : new_user.username,
        "email"             : new_user.email,
        "phone"             : new_user.phone,
        "legal_address"     : new_user.legal_address,
        "user_city"         : new_user.user_city,
        "user_department"   : new_user.user_department,
        "id_number"         : new_user.id_number,
        "user_status"       : new_user.user_status
    }

    return user_data


def create_access_token(username: str, role: str, user_id:str, user_pk:int, user_st:str, expires_delta: timedelta = None):
    to_encode = {
        "sub"   : username,
        "role"  : role,
        "id"    : user_id,
        "pk"    : user_pk,
        "st"    : user_st
    }
    if expires_delta:
        expire = datetime.now() + expires_delta 
    else:
        expire = datetime.now() + timedelta(minutes=15)
    to_encode.update({"exp": expire.timestamp()})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

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

@router.post("/affiliate/user/create/")  # Logs for Affiliate Users
async def create_affiliate_user(
    user_in: UserIn,
    db: Session = Depends(get_db),
    token: str = Header(None)
): 
    
    # Check if token is provided 
    agent_id = None
    if token:
        decoded_token = decode_jwt(token)
        role_from_token = decoded_token.get("role")
        user_id_from_token = decoded_token.get("id")
        agent_id = decoded_token.get("pk")

        if role_from_token.lower() not in ["admin", "agent"]:
            raise HTTPException(status_code=403, detail="Unauthorized to create affiliate users")
    else:
        # If no token, and agent_id is provided directly in the request
        agent_id = user_in.added_by if user_in.added_by else None

    # Check for existing users with the same credentials
    existing_user = db.query(UserInDB).filter(UserInDB.username == user_in.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Usuario ya esta en uso")

    existing_user = db.query(UserInDB).filter(UserInDB.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email ya esta en uso")

    existing_user = db.query(UserInDB).filter(UserInDB.phone == user_in.phone).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Nro telefonico ya fue registrado")

    existing_user = db.query(UserInDB).filter(UserInDB.id_number == user_in.id_number).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Ya hay un usuario credo con ese ID")

    temp_password = create_temp_password(user_in.username)
    hashed =pwd_context.hash(temp_password)    

    new_user = UserInDB(
        role            = user_in.role,
        username        = user_in.username,
        email           = user_in.email,
        hashed_password = hashed,
        phone           = user_in.phone,
        legal_address   = user_in.legal_address,
        user_city       = user_in.user_city,
        user_department = user_in.user_department,
        id_number       = user_in.id_number,
        added_by        = agent_id
    )
    new_user.agent = False    
    new_user.user_status = "temp_password"    

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    #send email to username with email + temp_password
    sender_email    = "no-reply@mail.app.actyvalores.com" 
    receiver_email  = user_in.email
    subject         = "Usuario Creado"
    body            = "Hola, hemos creado tu usuario para Activos & Valores"
    body_html = f"""\
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
            .content {{ background-color: #f4f4f4; padding: 20px; border-radius: 10px; }}
            .footer {{ padding-top: 20px; color: #666; }}
            a {{ color: #0073AA; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .button-link {{ 
                padding: 10px 20px; 
                background-color: #0A8CBF; 
                color: white; 
                border-radius: 5px; 
                text-align: center; 
                display: inline-block;
            }}
        </style>
    </head>
    <body>
        <div class="content">
            <h1>Bienvenido a Activos & Valores</h1>
            <p>Hola,</p>
            <p>Se ha creado tu usuario para Activos & Valores. Ahora podrás ingresar para dar seguimiento a tus solicitudes. Por favor, accede al sistema usando el siguiente enlace:</p>
            <p style="text-align: center;">
                <a href='https://app.actyvalores.com/' class="button-link">Acceder a Activos & Valores</a>
            </p>
            <p>Utiliza la siguiente contraseña temporal para ingresar: <strong>{temp_password}</strong></p>
            <p>Te recomendamos cambiar tu contraseña después de iniciar sesión por primera vez.</p>
        </div>
        <div class="footer">
            <p>Saludos,<br>Equipo de Desarrollo<br><a href="https://app.actyvalores.com">actyvalores.com</a></p>
        </div>
    </body>
    </html>

    """


    # with smtplib.SMTP(smtp_host, 587) as server:
    #         server.starttls()
    #         server.login(smtp_user, smtp_password) 
    #         msg = MIMEMultipart('alternative')
    #         msg['Subject'] = subject
    #         msg['From'] = sender_email
    #         msg['To'] = receiver_email
    #         part1 = MIMEText(body, 'plain')
    #         part2 = MIMEText(body_html, 'html')
    #         msg.attach(part1)
    #         msg.attach(part2)
    #         server.sendmail(sender_email, receiver_email, msg.as_string())

    if token:
        log_entry = LogsInDb(
            action      = "User Created",
            timestamp   = local_timestamp_str,
            message     = f"User with username '{user_in.username}' has been registered by {role_from_token}",
            user_id     = user_id_from_token
        )
    else:
        log_entry = LogsInDb(
            action      = "User Created",
            timestamp   = local_timestamp_str,
            message     = f"User '{user_in.username}' registered under agent {agent_id}",
            user_id     = new_user.id  # Use the newly created user's ID
        )
    db.add(log_entry)
    db.commit()
    
    
    return {"message": f"Has creado el usuario '{user_in.username}'"
            
            }
    


@router.post("/user/auth/")  #LOGS
async def auth_user(user_au: UserAuth, db: Session = Depends(get_db)):
    input_email = user_au.email.lower()
    user_in_db = db.query(UserInDB).filter(func.lower(UserInDB.email) == input_email).first()
    if not user_in_db:
        raise HTTPException(status_code=404, detail="El usuario no existe")
        
    if not pwd_context.verify(user_au.password, user_in_db.hashed_password):
        raise HTTPException(status_code=403, detail="Error de autenticacion")

    log_entry = LogsInDb(
        action          = "User Logged",
        timestamp       = local_timestamp_str,
        message         = f"User with username '{user_in_db.username}' has entered the app",
        user_id         = user_in_db.id_number
    )
    db.add(log_entry)
    db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        username        = user_in_db.username,
        role            = user_in_db.role,
        user_id         = user_in_db.id_number,
        user_pk         = user_in_db.id,
        user_st         = user_in_db.user_status,
        expires_delta   = access_token_expires
    )
    response = {
        "Autenticado": True,
        "access_token": access_token,
        "user_status" : user_in_db.user_status  #line added to stablish global variable
    }
    return response


@router.get("/user/perfil/{user_info_ask}")  # LOGS
async def get_mi_perfil(user_info_ask: str, db: Session = Depends(get_db), token: str = Header(None)):
    
    # Decodificar el token y obtener la información del usuario
    decoded_token       = decode_jwt(token)
    user_id_from_token  = decoded_token.get("id")
    role_from_token     = decoded_token.get("role")

    # Validar que el id en el token coincida con el solicitado o que sea admin
    if user_info_ask != user_id_from_token and role_from_token != "admin":
        raise HTTPException(status_code=403, detail="No tienes acceso a este perfil")

    # Obtener información del usuario en la base de datos
    user_info = db.query(UserInDB).filter_by(id_number=user_info_ask).first()
    if not user_info:
        raise HTTPException(status_code=404, detail="El usuario no existe")

    # Obtener documentos asociados al usuario
    user_files = db.query(File).filter(File.entity_id == user_info.id).all()
    documents_status = {
        "cedula_front"      : None,
        "cedula_back"       : None,
        "tax_id_file"       : None,
        "bank_certification": None,
        "profile_picture"   : None,
        "professional_card" : None  # Agregamos la tarjeta profesional para los abogados
    }

    # Generar URLs prefirmadas para cada documento si existen
    for file in user_files:
        if file.file_type in documents_status:
            presigned_url = generate_presigned_url(file.file_location, expiration=3600)
            documents_status[file.file_type] = {
                "uploaded"  : presigned_url is not None,
                "path"      : presigned_url
            }

    # Crear el diccionario con la información del usuario y documentos
    user_info_dict = {
        "username"         : user_info.username,
        "id_number"        : user_info.id_number,
        "civil_status"     : user_info.civil_status, 
        "email"            : user_info.email,
        "phone"            : user_info.phone,
        "legal_address"    : user_info.legal_address,
        "user_city"        : user_info.user_city,
        "user_department"  : user_info.user_department,
        "tax_id"           : user_info.tax_id,
        "bank_name"        : user_info.bank_name,
        "account_type"     : user_info.account_type,
        "account_number"   : user_info.account_number,
        "documents": [
            {"name": "Cedula cara frontal", "key": "cedula_front", "uploaded": documents_status["cedula_front"] is not None, "path": documents_status["cedula_front"]["path"] if documents_status["cedula_front"] else None},
            {"name": "Cedula cara posterior", "key": "cedula_back", "uploaded": documents_status["cedula_back"] is not None, "path": documents_status["cedula_back"]["path"] if documents_status["cedula_back"] else None},
            {"name": "Rut", "key": "tax_id_file", "uploaded": documents_status["tax_id_file"] is not None, "path": documents_status["tax_id_file"]["path"] if documents_status["tax_id_file"] else None},
            {"name": "Certificación bancaria", "key": "bank_certification", "uploaded": documents_status["bank_certification"] is not None, "path": documents_status["bank_certification"]["path"] if documents_status["bank_certification"] else None},
            {"name": "Foto de Perfil", "key": "profile_picture", "uploaded": documents_status["profile_picture"] is not None, "path": documents_status["profile_picture"]["path"] if documents_status["profile_picture"] else None},
            {"name": "Tarjeta Profesional", "key": "professional_card", "uploaded": documents_status["professional_card"] is not None, "path": documents_status["professional_card"]["path"] if documents_status["professional_card"] else None}
        ]
    }

    if role_from_token == "admin":
        user_info_dict.update({
            "role"  : user_info.role
        })
    
    return user_info_dict


@router.post("/user/info/")  # LOGS # TOKEN
async def get_user_info(user_info_ask: UserInfoAsk, db: Session = Depends(get_db), 
                        token: str = Header(None)):

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    # Validar permisos
    if role_from_token not in ["admin", "agent", "lawyer"]:
        raise HTTPException(status_code=403, detail="No tienes permiso de ver esta información")

    user = db.query(UserInDB).filter_by(id_number=user_info_ask.id_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    role = user.role
    mortgages = 0
    total_debt = 0
    lendings = 0
    invested = 0

    # Lógica para el rol "debtor"
    if role == "debtor":
        mortgages_query = db.query(MortgageInDB).filter_by(debtor_id=user.id_number).all()
        mortgages = len(mortgages_query)
        total_debt = sum(mortgage.initial_balance for mortgage in mortgages_query)

        return {
            "role": role,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "mortgages": mortgages,
            "total_debt": total_debt,
        }

    # Lógica para el rol "lender"
    elif role == "lender":
        lendings_query = db.query(MortgageInDB).filter_by(lender_id=user.id_number).all()
        lendings = len(lendings_query)
        invested = sum(mortgage.initial_balance for mortgage in lendings_query)

        return {
            "role": role,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "lendings": lendings,
            "invested": invested,
        }

    # Lógica para el rol "agent"
    elif role == "agent":

        return {
            "role": role,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
        }

    # Lógica para el rol "lawyer"
    elif role == "lawyer":

        return {
            "role": role,
            "username": user.username,
            "email": user.email,
            "phone": user.phone
        }

    

@router.get("/admin_panel/users/")  # Logs for Admin and Agent, token required
async def get_all_users(
    db: Session = Depends(get_db),
    token: str = Header(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role    = decoded_token.get("role")
    user_id = decoded_token.get("id")
    user_pk = decoded_token.get("pk")  # Added primary key of the agent

    is_first_login = False

    if role == "admin":
        # Retrieve all users
        users       = db.query(UserInDB).all() 
        user_info   = []
        for user in users:
            user_info.append({
                "role"      : user.role,
                "username"  : user.username,
                "email"     : user.email,
                "phone"     : user.phone,
                "id_number" : user.id_number
            })
        return user_info

    elif role == "agent" or role == "lawyer":
        # Retrieve users added by the agent
        last_logs_count = db.query(LogsInDb).filter(LogsInDb.user_id == user_id).count()
        # Si el usuario tiene menos de 3 registros, lo consideramos su primera vez
        if last_logs_count < 3:
            is_first_login = True
        else:
            is_first_login = False

        users_added_by_agent = db.query(UserInDB).filter(UserInDB.added_by == user_pk).all()
        user_info = []
        for user in users_added_by_agent:
            loan_requests = db.query(PropInDB).filter(PropInDB.owner_id == user.id_number).all()
            solicitudes = [{
                "property_id"   : request.id, # Assuming there's an ID field
                "matricula_id"  : request.matricula_id,
                "address"       : request.address,
                "neighbourhood" : request.neighbourhood,
                "city"          : request.city,
                "department"    : request.department,
                "strate"        : request.strate,
                "area"          : request.area,
                "type"          : request.type,
                "tax_valuation" : request.tax_valuation,
                "loan_solicited": request.loan_solicited
                # Include any other fields from PropInDB here
            } for request in loan_requests]
            user_info.append({
                "username"      : user.username,
                "role"          : user.role,
                "id_number"     : user.id_number,
                "email"         : user.email,
                "phone"         : user.phone,
                "status"        : user.user_status,
                "solicitudes"   : solicitudes if solicitudes else "Ninguna"
            })
        return {"users": user_info, "is_first_login": is_first_login}
    else:
        raise HTTPException(status_code=403, detail="No tienes permiso de ver esta información")
 

@router.get("/agent/clients/")  # Logs for Admin and Agent, token required
async def get_all_users(
    db: Session = Depends(get_db),
    token: str = Header(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role    = decoded_token.get("role")
    user_pk = decoded_token.get("pk")  # Added primary key of the agent

    if role == "agent" or "admin" or "lawyer":
        users_added_by_agent = db.query(UserInDB).filter(UserInDB.added_by == user_pk).all()
        user_info = []
        for user in users_added_by_agent:
            if user.role == 'debtor':
                user_info.append({
                    "username"      : user.username,
                    "role"          : user.role,
                    "id_number"     : user.id_number,
                    "email"         : user.email,
                    "phone"         : user.phone,
                    "status"        : user.user_status,
                })
        return user_info
    else:
        raise HTTPException(status_code=403, detail="No tienes permiso de ver esta información")

@router.get("/admin_summary")
def admin_summary(db: Session = Depends(get_db), token: str = Header(None)):

    # Token verification 
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      ="User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to admin summary (Token not provided)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token   = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="Insufficient privileges")
 
    # Get total count of mortgages, registers, and users
    total_mortgages = db.query(func.count(MortgageInDB.id)).scalar()
    total_users     = db.query(func.count(UserInDB.id)).scalar()

    # Get total amounts for mortgages and registers
    total_mortgage_amount = db.query(func.sum(MortgageInDB.current_balance)).scalar()
    if not total_mortgage_amount :
        total_mortgage_amount = 0

    # Get the number of pending payments
    pending_payments = db.query(func.count(RegsInDb.id)).filter(RegsInDb.payment_status == "pending").scalar()

    # Get the number of active mortgages
    active_mortgages = db.query(func.count(MortgageInDB.id)).filter(MortgageInDB.mortgage_status == "active").scalar()

    # Get the number of mortgages with specific statuses
    debt_pending_mortgages = db.query(func.count(MortgageInDB.id)).filter(MortgageInDB.mortgage_status == "debt_pending").scalar()
    
    lawyer_mortgages = db.query(func.count(MortgageInDB.id)).filter(MortgageInDB.mortgage_status == "debt_pending").scalar()
    
    
    # Get the number of users with specific roles
    admin_users     = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "admin").scalar()
    debtor_users    = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "debtor").scalar()
    lender_users    = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "lender").scalar()
    agent_users     = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "agent").scalar()

    # Get the last penalty set
    current_month = local_now.month
    current_year = local_now.year

    # Check if there is any penalty for the current month
    penalties = (
        db.query(PenaltyInDB)
        .filter(
            func.extract("year", PenaltyInDB.start_date) == current_year,
            func.extract("month", PenaltyInDB.start_date) == current_month
        )
        .first()
    )

    # Check if any penalty is found
    if penalties:
        penalty_status = "actualizado"
    else:
        penalty_status = "vencido"

    # Get the number of properties with specific statuses
    received_props  = db.query(func.count(PropInDB.id)).filter(PropInDB.study != "approved").scalar()
    posted_props    = db.query(func.count(PropInDB.id)).filter(PropInDB.study == "approved").scalar()
    selected_props  = db.query(func.count(PropInDB.id)).filter(PropInDB.prop_status == "selected").scalar()
    

    # Construct the summary dictionary
    summary = {
        "total_mortgages"           : total_mortgages,
        "total_users"               : total_users,
        "total_mortgage_amount"     : total_mortgage_amount,
        "pending_payments"          : pending_payments,
        "active_mortgages"          : active_mortgages,
        "debt_pending_mortgages"    : debt_pending_mortgages,
        "lawyer_mortgages"          : lawyer_mortgages,
        "admin_users"               : admin_users,
        "debtor_users"              : debtor_users,
        "lender_users"              : lender_users,
        "agent_users"               : agent_users,
        "last_penalty"              : penalty_status,
        "received_props"            : received_props,
        "posted_props"              : posted_props,
        "selected_props"            : selected_props,
    }
    return summary



@router.get("/all_registers")
def get_all_registers(db: Session = Depends(get_db), token: str = Header(None)):
    
    # Token verification
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token   = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    # Get all registers
    all_registers = db.query(RegsInDb).all()

    return all_registers

@router.put("/update_user_info/{id_number}")
async def update_user_info(
    id_number: str,
    tax_id_file         : UploadFile = FastAPIFile(None),
    cedula_front        : UploadFile = FastAPIFile(None),
    cedula_back         : UploadFile = FastAPIFile(None),
    bank_certification  : UploadFile = FastAPIFile(None), 
    profile_picture     : UploadFile = FastAPIFile(None),
    professional_card   : UploadFile = FastAPIFile(None),  # Nuevo campo para abogados
    user_data           : str = Form(...),
    db                  : Session = Depends(get_db),
    token               : str = Header(None)
):
    
    try:
        data = json.loads(user_data)
        print("User data:", data)
    except json.JSONDecodeError as e:
        print("Error parsing user_data:", str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON format for user_data")
    
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    user_id_from_token  = decoded_token.get("id")

    user = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Parsing user_data from JSON
    try:
        data = json.loads(user_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for user_data")

    # Update user information based on data
    user.legal_address  = data.get('legal_address', user.legal_address)
    user.phone          = data.get('phone', user.phone)
    user.user_city      = data.get('user_city', user.user_city)
    user.user_department= data.get('user_department', user.user_department) 
    user.account_type   = data.get('account_type', user.account_type)
    user.account_number = data.get('account_number', user.account_number)
    user.bank_name      = data.get('bank_name', user.bank_name)
    user.tax_id         = data.get('tax_id', user.tax_id)
    user.civil_status   = data.get('civil_status', user.civil_status)

    # Process and save files
    files = {
        "tax_id_file"       : tax_id_file,
        "cedula_front"      : cedula_front,
        "cedula_back"       : cedula_back,
        "bank_certification": bank_certification,
        "profile_picture"   : profile_picture,
        "professional_card" : professional_card 
    }
    s3_bucket_name = 'actyfiles'
    for file_key, file in files.items():
        if file:
            object_name = f"{id_number}_{file_key}_{file.filename}"  # Simple key without folder paths
            try:
                s3_client.upload_fileobj(file.file, s3_bucket_name, object_name)
                # Save the reference in the database if necessary
                save_file_to_s3_db(db, "user", user.id, file_key, object_name)
            except Exception as e:
                print(f"Failed to upload {file.filename}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}")

    log_entry = LogsInDb(
        action      = "User Information Updated",
        timestamp   = local_timestamp_str,
        message     = f"Information updated for user with ID: {id_number}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()
    
    db_user             = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()
    user_info_complete  = validate_user_info(db_user)
    user_status         = "complete" if user_info_complete else "incomplete"
    db_user.user_status = user_status
    db.commit()

    return {"message": "Información de usuario actualizada correctamente"}


@router.get("/mail_check/{email}")
async def check_mail(email: str, db: Session = Depends(get_db)):
    email = email.lower().strip()    
    user = db.query(UserInDB).filter(UserInDB.email == email).first()
    
    if not user:
        
        log_entry = LogsInDb(
            action      = "ALERTA! Recuperacion de contraseña correo inexistente",
            timestamp   = local_timestamp_str,
            message     = f"Correo usuario intentado: {email}",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()
        
        raise HTTPException(status_code=404, detail="No se encontró un usuario con este correo electrónico.")

    if user:
        oob_code = secrets.token_urlsafe(64)
        # Email setup
        sender_email    = "no-reply@mail.app.actyvalores.com" 
        receiver_email  = email
        subject         = "Recuperacion de contraseña"
        body            = "Hola, si has solicitado recuperar tu contraseña de la APP Actyvalores, por favor has click en el link para asignar una nueva contraseña:"
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
                <h1>Recuperación de Contraseña</h1>
                <p>Hola,</p>
                <p>Si has solicitado recuperar tu contraseña de la APP Actyvalores, por favor haz click en el siguiente botón para asignar una nueva contraseña:</p>
                <p style="text-align: center;">
                    <a href='https://app.actyvalores.com/auth/action/{email}?mode=resetPassword&oobCode={oob_code}&apiKey=AIzaSyAo1OXXBKkJ0T_HHMiW2Df-KumPJrQU94I&lang=es-419' style='padding: 10px 20px; background-color: #0A8CBF; color: white; border-radius: 5px; text-align: center; display: inline-block;'>Restablecer Contraseña</a>
                </p>
            </div>
            <div class="footer">
                <p>Si no has solicitado este cambio, por favor ignora este mensaje.</p>
                <p>Saludos,<br>Equipo de Desarrollo</p>
                <p><a href="https://app.actyvalores.com">actyvalores.com</a></p>
            </div>
        </body>
        </html>
        """

        # with smtplib.SMTP(smtp_host, 587) as server:
        #     server.starttls()
        #     server.login(smtp_user, smtp_password) 
        #     msg = MIMEMultipart('alternative')
        #     msg['Subject'] = subject
        #     msg['From'] = sender_email
        #     msg['To'] = receiver_email
        #     part1 = MIMEText(body, 'plain')
        #     part2 = MIMEText(body_html, 'html')
        #     msg.attach(part1)
        #     msg.attach(part2)
        #     server.sendmail(sender_email, receiver_email, msg.as_string())

        # return {"exists": True, "message": "A recovery email has been sent if the address is registered with us."}
    
    
@router.put("/update_password/{email}")
async def update_password(email: str, password_change: PasswordChange, db: Session = Depends(get_db)):
    db_user = db.query(UserInDB).filter(UserInDB.email == email).first()
    password = password_change.password_change
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = pwd_context.hash(password)
    db_user.hashed_password = hashed_password
    
    db.commit()
    db.refresh(db_user)
    
    db_user = db.query(UserInDB).filter(UserInDB.id_number == db_user.id_number).first()
    user_info_complete = validate_user_info(db_user)
    user_status = "complete" if user_info_complete else "incomplete"
    db_user.user_status = user_status
    db.commit()

    # Log the successful password change
    log_entry = LogsInDb(
        action      = "Cambio de Contraseña Exitoso",
        timestamp   = local_timestamp_str,
        message     = f"Correo {email}",
        user_id     = db_user.id_number  
    )
    db.add(log_entry)
    db.commit()
    
    new_token = create_access_token(db_user.username, db_user.role, str(db_user.id_number), db_user.id, user_status)

    return {"message": "Tu contraseña se ha cambiado exitosamente", "new_token": new_token}

@router.put("/user/update/{id_number}")
async def update_user_info(
    id_number: str,
    user_data: dict,  # Esperamos los datos de usuario como un diccionario
    token: str = Header(None),  # Recibimos el token en los headers
    db: Session = Depends(get_db)
):
    # Decodificamos el token para obtener la información del usuario
    decoded_token = decode_jwt(token)
    user_id_from_token = decoded_token.get("id")
    role_from_token = decoded_token.get("role")

    # Validamos si el usuario tiene permiso (admin o el propio usuario)
    if user_id_from_token != id_number and role_from_token != "admin":
        raise HTTPException(status_code=403, detail="No tienes permisos para realizar esta acción")

    # Buscamos el usuario en la base de datos
    user = db.query(UserInDB).filter_by(id_number=id_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Actualizamos los campos del usuario según los datos recibidos
    if "username" in user_data:
        user.username = user_data["username"]
    if "id_number" in user_data:
        user.id_number = user_data["id_number"]
    if "email" in user_data:
        user.email = user_data["email"]
    if "phone" in user_data: 
        user.phone = user_data["phone"]
    if "legal_address" in user_data:
        user.legal_address = user_data["legal_address"]
    if "user_city" in user_data:
        user.user_city = user_data["user_city"]
    if "user_department" in user_data:
        user.user_department = user_data["user_department"]
    if "tax_id" in user_data:
        user.tax_id = user_data["tax_id"]
    if "bank_name" in user_data:
        user.bank_name = user_data["bank_name"]
    if "account_type" in user_data:
        user.account_type = user_data["account_type"]
    if "account_number" in user_data:
        user.account_number = user_data["account_number"]

    # Guardamos los cambios en la base de datos
    db.commit()

    return {"message": "Información actualizada correctamente", "user_data": user_data}