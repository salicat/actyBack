from fastapi import Depends, APIRouter, HTTPException, Header, UploadFile, File as FastAPIFile, Form
from sqlalchemy.orm import Session 
from db.db_connection import get_db
from db.all_db import UserInDB, MortgageInDB, LogsInDb, RegsInDb, PropInDB, PenaltyInDB, File
from models.user_models import UserIn, UserAuth, UserInfoAsk
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
import json
import os
import shutil

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

utc_now                 = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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
                   ]
}

def validate_user_info(user: UserInDB) -> bool:
    required_fields = required_fields_by_role.get(user.role, [])
    user_data = user.__dict__ 
    for field in required_fields:
        if field not in user_data or not user_data[field]:
            return False
    return True


@router.post("/user/create/")  # LOGS
async def create_user(user_in: UserIn, db: Session = Depends(get_db)):
    allowed_roles = ["admin", "lender", "debtor", "agent"]  
    for user in user_in:
        print(user)
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
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decode token to extract role and id 
    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")
    user_id_from_token  = decoded_token.get("id")
    agent_id            = decoded_token.get("pk")

    # Check if role is valid for creating affiliate users
    if role_from_token.lower() not in ["admin", "agent"]:
        raise HTTPException(status_code=403, detail="Unauthorized to create affiliate users")

    # Check if role is allowed
    allowed_roles = ["admin", "lender", "debtor", "agent"]  
    if user_in.role.lower() not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role. Allowed roles are: admin, lender, debtor, agent")

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

    hashed_password = pwd_context.hash(user_in.id_number )
   
    new_user = UserInDB(
        role            = user_in.role,
        username        = user_in.username,
        email           = user_in.email,
        hashed_password = hashed_password,
        phone           = user_in.phone,
        legal_address   = user_in.legal_address,
        user_city       = user_in.user_city,
        user_department = user_in.user_department,
        id_number       = user_in.id_number,
        added_by        = agent_id
    )

    new_user.agent = False    
    new_user.user_status = "incomplete"    

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_entry = LogsInDb(
        action      = "User Created",
        timestamp   = local_timestamp_str,
        message     = f"User with username '{user_in.username}' has been registered by {role_from_token}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    return {"message": f"Has creado el usuario '{user_in.username}'"}


@router.post("/user/auth/")  #LOGS
async def auth_user(user_au: UserAuth, db: Session = Depends(get_db)):
    input_email = user_au.email.lower()
    user_in_db = db.query(UserInDB).filter(func.lower(UserInDB.email) == input_email).first()
    if not user_in_db:
        # Log failed login attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"User with email '{user_au.email}' does not exist",
            user_id     = None  
        ) 
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=404, detail="El usuario no existe")
        
    if not pwd_context.verify(user_au.password, user_in_db.hashed_password):
        # Log failed login attempt due to wrong password
        log_entry       = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"User with email '{user_au.email}' entered the wrong password",
            user_id     = user_in_db.id_number
        )
        db.add(log_entry)
        db.commit()
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
async def get_mi_perfil(user_info_ask: str, db: Session = Depends(get_db)):
    user_info = db.query(UserInDB).filter_by(id_number=user_info_ask).first()
    if not user_info:
        raise HTTPException(status_code=404, detail="El usuario no existe")

    log_entry = LogsInDb(
        action      = "Profile Accessed",
        timestamp   = local_timestamp_str,
        message     = f"Profile accessed for user with ID '{user_info_ask}' (Username: {user_info.username})",
        user_id     = user_info.id_number
    )
    db.add(log_entry)
    db.commit()

    
    user_files = db.query(File).filter(File.entity_id == user_info.id).all()  # Assuming 'entity_id' references 'UserInDB.id'
    documents_status = {
        "cedula_front": None,
        "cedula_back": None,
        "tax_id_file": None,
        "bank_certification": None,
        "profile_picture" : None
    }

    # Update to check file existence and include path
    for file in user_files:
        file_key = None
        if file.file_type == "cedula_front":
            file_key = "cedula_front"
        elif file.file_type == "cedula_back":
            file_key = "cedula_back"
        elif file.file_type == "tax_id_file":
            file_key = "tax_id_file"
        elif file.file_type == "bank_certification":
            file_key = "bank_certification"
        elif file.file_type == "profile_picture":
            file_key = "profile_picture"
        
        if file_key:
            documents_status[file_key] = {"uploaded": True, "path": file.file_location}

    user_info_dict = {
        "username"          : user_info.username,
        "email"             : user_info.email,
        "phone"             : user_info.phone,
        "legal_address"     : user_info.legal_address,
        "user_city"         : user_info.user_city,
        "user_department"   : user_info.user_department,
        "id_number"         : user_info.id_number,
        "tax_id"            : user_info.tax_id,
        "bank_name"         : user_info.bank_name,
        "account_type"      : user_info.account_type,
        "account_number"    : user_info.account_number,
        "documents": [
            {"name": "Cedula cara frontal", "key": "cedula_front", "uploaded": documents_status["cedula_front"] != None, "path": documents_status["cedula_front"]["path"] if documents_status["cedula_front"] else None},
            {"name": "Cedula cara posterior", "key": "cedula_back", "uploaded": documents_status["cedula_back"] != None, "path": documents_status["cedula_back"]["path"] if documents_status["cedula_back"] else None},
            {"name": "Rut", "key": "tax_id_file", "uploaded": documents_status["tax_id_file"] != None, "path": documents_status["tax_id_file"]["path"] if documents_status["tax_id_file"] else None},
            {"name": "Certificacion bancaria", "key": "bank_certification", "uploaded": documents_status["bank_certification"] != None, "path": documents_status["bank_certification"]["path"] if documents_status["bank_certification"] else None},
            {"name": "Foto de Perfil", "key": "profile_picture", "uploaded": documents_status["profile_picture"] !=None, "path": documents_status["profile_picture"]["path"] if documents_status["profile_picture"] else None}             
            ]
        }
    return user_info_dict


@router.post("/user/info/")  #LOGS #TOKEN
async def get_user_info(user_info_ask: UserInfoAsk, db: Session = Depends(get_db), 
    token: str = Header(None)):

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token is None:
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to user information (Invalid or missing role in the token)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit()
        
    if role_from_token != "admin":
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to user information (Insufficient permissions)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso de ver esta informacion")

    user = db.query(UserInDB).filter_by(id_number=user_info_ask.id_number).first()
    if not user:
        log_entry       = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"User information access failed for user with ID '{user_info_ask.id_number}' (User not found)",
            user_id     = None  # You can leave user_id as None for non-existent users
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=404, detail="User not found")

    log_entry = LogsInDb(
        action      = "User Info Accessed",
        timestamp   = local_timestamp_str,
        message     = f"User information accessed for user with ID '{user_info_ask.id_number}' (Username: {user.username})",
        user_id     = user.id_number
    )
    db.add(log_entry)
    db.commit()

    role = user.role
    mortgages   = 0 
    total_debt  = 0
    lendings    = 0 
    invested    = 0
    
    if role == "debtor":
        mortgages_query = db.query(MortgageInDB).filter_by(debtor_id=user.id_number).all()
        mortgages       = len(mortgages_query)
        total_debt      = sum(mortgage.initial_balance for mortgage in mortgages_query)

        return {
        "role"              : role,
        "username"          : user.username,
        "email"             : user.email,
        "phone"             : user.phone,
        "mortgages"         : mortgages,
        "total_debt"        : total_debt,
    }

    elif role == "lender":
        lendings_query  = db.query(MortgageInDB).filter_by(lender_id=user.id_number).all()
        lendings        = len(lendings_query)
        invested        = sum(mortgage.initial_balance for mortgage in lendings_query)

        return {
        "role"              : role,
        "username"          : user.username,
        "email"             : user.email,
        "phone"             : user.phone,
        "lendings"          : lendings,
        "invested"          : invested
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

    if role == "admin":
        # Log user information access by admin
        log_entry = LogsInDb(
            action      ="User Information Accessed",
            timestamp   = local_timestamp_str,
            message     = f"Users information accessed by {role} (User ID: {user_id})",
            user_id     = user_id
        )
        db.add(log_entry)
        db.commit()

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

    elif role == "agent":
        # Log user information access by agent
        log_entry = LogsInDb(
            action      = "User Information Accessed",
            timestamp   = local_timestamp_str,
            message     = f"Users information accessed by {role} (User ID: {user_id})",
            user_id     = user_id
        )
        db.add(log_entry)
        db.commit()

        # Retrieve users added by the agent
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
        return user_info
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

    if role == "agent" or "admin":
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
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to admin summary (Insufficient privileges)",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
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


    # Log successful access to admin summary
    log_entry = LogsInDb(
        action      = "Admin Summary Accessed",
        timestamp   = local_timestamp_str,
        message     = "Admin summary accessed successfully",
        user_id     = decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    return summary



@router.get("/all_registers")
def get_all_registers(db: Session = Depends(get_db), token: str = Header(None)):
    
    # Token verification
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to all registers (Token not provided)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token   = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to all registers (Insufficient privileges)",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    # Get all registers
    all_registers = db.query(RegsInDb).all()

    # Log successful access to all registers
    log_entry = LogsInDb(
        action      = "All Registers Accessed",
        timestamp   = local_timestamp_str,
        message     = "All registers accessed successfully",
        user_id     = decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    return all_registers

@router.put("/update_user_info/{id_number}")
async def update_user_info(
    id_number: str,
    tax_id_file         : UploadFile = FastAPIFile(None),
    cedula_front        : UploadFile = FastAPIFile(None),
    cedula_back         : UploadFile = FastAPIFile(None),
    bank_certification  : UploadFile = FastAPIFile(None), 
    profile_picture     : UploadFile = FastAPIFile(None),
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
    user.account_type   = data.get('account_type', user.account_type)
    user.account_number = data.get('account_number', user.account_number)
    user.bank_name      = data.get('bank_name', user.bank_name)
    user.tax_id         = data.get('tax_id', user.tax_id)

    upload_folder = './uploads'
    os.makedirs(upload_folder, exist_ok=True)

    # Process and save files
    files = {
        "tax_id_file"       : tax_id_file,
        "cedula_front"      : cedula_front,
        "cedula_back"       : cedula_back,
        "bank_certification": bank_certification,
        "profile_picture"   : profile_picture
    }
    for file_key, file in files.items():
        if file:
            _, file_ext = os.path.splitext(file.filename)
            file_path   = os.path.join(upload_folder, f"{id_number}_{file_key}{file_ext}")
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            save_file_to_db(db, "user", user.id, file_key, file_path)

    log_entry = LogsInDb(
        action      = "User Information Updated",
        timestamp   = local_timestamp_str,
        message     = f"Information updated for user with ID: {id_number}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()
    
    db_user = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()
    user_info_complete = validate_user_info(db_user)
    user_status = "complete" if user_info_complete else "incomplete"
    db_user.user_status = user_status
    db.commit()

    return {"message": "Información de usuario actualizada correctamente"}

from fastapi import HTTPException

@router.get("/mail_check/{email}")
async def check_mail(email: str, db: Session = Depends(get_db)):
    email = email.lower().strip()
    user = db.query(UserInDB).filter(UserInDB.email == email).first()

    # Prepare and log the entry regardless of user existence
    log_entry = LogsInDb(
        action="Recuperacion de contraseña" if user else "ALERTA! Recuperacion de contraseña correo inexistente",
        timestamp   = local_timestamp_str,
        message     = f"Correo usuario: {email}",
        user_id     = None
    )
    db.add(log_entry)
    db.commit()

    if user:
        return {"exists": True, "message": "Un correo de recuperación será enviado si la dirección está registrada con nosotros."}
    else:
        raise HTTPException(status_code=404, detail="No se encontró un usuario con este email.")
