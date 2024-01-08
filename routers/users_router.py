from fastapi import Depends, APIRouter, HTTPException, Header
from sqlalchemy.orm import Session 
from db.db_connection import get_db
from db.all_db import UserInDB, MortgageInDB, LogsInDb, RegsInDb, PropInDB, PenaltyInDB
from models.user_models import UserIn, UserAuth, UserInfoAsk 
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from sqlalchemy import func

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

utc_now                 = datetime.utcnow() 
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()

@router.post("/user/create/")  #LOGS
async def create_user(user_in: UserIn, db: Session = Depends(get_db)):
    allowed_roles = ["admin", "lender", "debtor", "agent"]  
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
        raise HTTPException(status_code=400, detail="Nro telefonico ya fue registrado")
    existing_user = db.query(UserInDB).filter(UserInDB.id_number == user_in.id_number).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Ya hay un usuario credo con ese ID")

    hashed_password = pwd_context.hash(user_in.hashed_password)
    new_user = UserInDB(
        role            = user_in.role,
        username        = user_in.username,
        email           = user_in.email,
        hashed_password = hashed_password,
        phone           = user_in.phone,
        legal_address   = user_in.legal_address,
        user_city       = user_in.user_city,
        user_department = user_in.user_department,
        id_number       = user_in.id_number
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_entry       = LogsInDb(
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
        "id_number"         : new_user.id_number
    }

    return user_data

def create_access_token(username: str, role: str, user_id:str, user_pk:int , expires_delta: timedelta = None):
    to_encode = {
        "sub"   : username,
        "role"  : role,
        "id"    : user_id,
        "pk"    : user_pk
    }
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
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


@router.post("/user/auth/")  #LOGS
async def auth_user(user_au: UserAuth, db: Session = Depends(get_db)):
    user_in_db = db.query(UserInDB).filter_by(email=user_au.email).first()
    if not user_in_db:
        # Log failed login attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = datetime.utcnow(),
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
            timestamp   = datetime.utcnow(),
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
        expires_delta   = access_token_expires
    )
    response = {
        "Autenticado": True,
        "access_token": access_token
    }
    return response

@router.get("/user/perfil/{user_info_ask}") #LOGS
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

    user_info_dict = {
        "role"              : user_info.role,
        "username"          : user_info.username,
        "email"             : user_info.email,       
        "phone"             : user_info.phone, 
        "legal_address"     : user_info.legal_address,
        "user_city"         : user_info.user_city,
        "user_department"   : user_info.user_department,
        "id_number"         : user_info.id_number,
        "tax_id"            : user_info.tax_id,
        "score"             : user_info.score,
        "user_status"       : user_info.user_status,
        "bank_account"      : user_info.bank_account,
        "account_number"    : user_info.account_number,
        "bank_name"         : user_info.bank_name,
        "agent"             : user_info.agent,
        "added_by"          : user_info.added_by
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
    

@router.get("/admin_panel/users/") #LOGS #TOKEN
async def get_all_users(db: Session = Depends(get_db), token: str = Header(None)):
    if token:
        decoded_token   = decode_jwt(token)
        role            = decoded_token.get("role")
        user_id         = decoded_token.get("id")
        
        if role == "admin" or role == "agent":
            log_entry = LogsInDb(
                action      = "User Information Accessed",
                timestamp   = local_timestamp_str,
                message     = f"Users information accessed by {role} (User ID: {user_id})",
                user_id     = user_id
            )
            db.add(log_entry)
            db.commit()

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
        else:
            raise HTTPException(status_code=403, detail="No tienes permiso de ver esta informacion")
    else:
        raise HTTPException(status_code=401, detail="Token not provided")



@router.get("/admin_summary")
def admin_summary(db: Session = Depends(get_db), token: str = Header(None)):

    # Token verification
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized access attempt to admin summary (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized access attempt to admin summary (Insufficient privileges)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    # Get total count of mortgages, registers, and users
    total_mortgages = db.query(func.count(MortgageInDB.id)).scalar()
    total_registers = db.query(func.count(RegsInDb.id)).filter(RegsInDb.amount > 0).scalar()
    total_users = db.query(func.count(UserInDB.id)).scalar()

    # Get total amounts for mortgages and registers
    total_mortgage_amount = db.query(func.sum(MortgageInDB.current_balance)).scalar()

    # Get the number of pending payments
    pending_payments = db.query(func.count(RegsInDb.id)).filter(RegsInDb.payment_status == "pending").scalar()

    # Get the number of active mortgages
    active_mortgages = db.query(func.count(MortgageInDB.id)).filter(MortgageInDB.mortgage_status == "active").scalar()

    # Get the number of mortgages with specific statuses
    debt_pending_mortgages = db.query(func.count(MortgageInDB.id)).filter(MortgageInDB.mortgage_status == "debt_pending").scalar()
    lawyer_mortgages = db.query(func.count(MortgageInDB.id)).filter(MortgageInDB.mortgage_status == "lawyer").scalar()

    # Get the number of users with specific roles
    admin_users = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "admin").scalar()
    debtor_users = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "debtor").scalar()
    lender_users = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "lender").scalar()
    agent_users = db.query(func.count(UserInDB.id)).filter(UserInDB.role == "agent").scalar()

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
    received_props = db.query(func.count(PropInDB.id)).filter(PropInDB.prop_status == "received").scalar()
    selected_props = db.query(func.count(PropInDB.id)).filter(PropInDB.prop_status == "selected").scalar()
    

    # Construct the summary dictionary
    summary = {
        "total_mortgages"           : total_mortgages,
        "total_users"               : total_users,
        "total_mortgage_amount"     : total_mortgage_amount,
        "pending_payments"          : pending_payments,
        "active_mortgages"          : active_mortgages,
        "debt_pending_mortgages"    : debt_pending_mortgages,
        "admin_users"               : admin_users,
        "debtor_users"              : debtor_users,
        "lender_users"              : lender_users,
        "agent_users"               : agent_users,
        "last_penalty"              : penalty_status,
        "received_props"            : received_props,
        "selected_props"            : selected_props,
    }


    # Log successful access to admin summary
    log_entry = LogsInDb(
        action="Admin Summary Accessed",
        timestamp=local_timestamp_str,
        message="Admin summary accessed successfully",
        user_id=decoded_token.get("id")
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
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized access attempt to all registers (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized access attempt to all registers (Insufficient privileges)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    # Get all registers
    all_registers = db.query(RegsInDb).all()

    # Log successful access to all registers
    log_entry = LogsInDb(
        action="All Registers Accessed",
        timestamp=local_timestamp_str,
        message="All registers accessed successfully",
        user_id=decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    return all_registers

    