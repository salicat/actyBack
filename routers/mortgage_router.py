from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import desc
from db.db_connection import get_db
from db.all_db import MortgageInDB, UserInDB, PropInDB, RegsInDb, PenaltyInDB, LogsInDb
from models.mortgage_models import MortgageCreate
from datetime import timedelta, date, datetime
import jwt

<<<<<<< HEAD
utc_now = datetime.utcnow()
=======
utc_now = datetime.utcnow() 
>>>>>>> c3c48f9 (Loan Applications update)
utc_offset = timedelta(hours=-5)
local_now = utc_now + utc_offset
local_timestamp_str = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

router = APIRouter()

SECRET_KEY = "8/8"
ALGORITHM = "HS256"

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


@router.post("/mortgages/create/") #LOGS #TOKEN-ROLE
<<<<<<< HEAD
def create_mortgage(mortgage_data: MortgageCreate, db: Session = Depends(get_db), token: str = Header(None)):
=======
def create_mortgage(mortgage_data   : MortgageCreate, 
                    db              : Session = Depends(get_db), 
                    token           : str = Header(None)):
>>>>>>> c3c48f9 (Loan Applications update)
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to create mortgage (Token not provided)",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token   = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token is None:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to create mortgage (Invalid or missing role in the token)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="Token is missing or invalid")

<<<<<<< HEAD
    if role_from_token != "admin":
        # Log unauthorized access attempt
=======
    if role_from_token != "admin": # Log unauthorized access attempt
>>>>>>> c3c48f9 (Loan Applications update)
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to create mortgage (Insufficient permissions)",
<<<<<<< HEAD
            user_id     = None  # You can leave user_id as None for unauthorized access
=======
            user_id     = None  
>>>>>>> c3c48f9 (Loan Applications update)
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para crear hipotecas")

    lender = db.query(UserInDB).filter(UserInDB.id_number == mortgage_data.lender_id).first()
    debtor = db.query(UserInDB).filter(UserInDB.id_number == mortgage_data.debtor_id).first()

<<<<<<< HEAD
    if not lender or not debtor:
        # Log invalid lender or debtor access attempt
=======
    if not lender or not debtor: # Log invalid lender or debtor access attempt
>>>>>>> c3c48f9 (Loan Applications update)
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Invalid lender or debtor ID in mortgage creation",
            user_id     = None  # You can leave user_id as None for unauthorized access
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=400, detail="Invalid lender or debtor ID")

    debtor_properties = db.query(PropInDB).filter(PropInDB.owner_id == debtor.id_number).all()

<<<<<<< HEAD
    if not debtor_properties:
        # Log user with no registered properties access attempt
=======
    if not debtor_properties: # Log user with no registered properties access attempt
>>>>>>> c3c48f9 (Loan Applications update)
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "El usuario no tiene inmuebles registrados",
            user_id     = decoded_token.get("id") if debtor else None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=400, detail="El usuario no tiene inmuebles registrados")

    property = db.query(PropInDB).filter(PropInDB.matricula_id == mortgage_data.matricula_id).first()

    if not property or property.owner_id != debtor.id_number:
        # Log unauthorized access attempt to create mortgage with a non-owned property
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "El prospecto deudor no es propietario del inmueble en referencia",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=400, detail="El prospecto deudor no es propietario del inmueble en referencia")

<<<<<<< HEAD
    if property.prop_status != "available":
=======
    if property.prop_status != "process":
>>>>>>> c3c48f9 (Loan Applications update)
        # Log unauthorized access attempt to create mortgage with an unavailable property
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Inmueble no disponible para hipoteca",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()

<<<<<<< HEAD
        raise HTTPException(status_code=400, detail="Inmueble no disponible para hipoteca")
=======
        raise HTTPException(
            status_code = 400, 
            detail      = "Inmueble no disponible para hipoteca"
        )
>>>>>>> c3c48f9 (Loan Applications update)

    new_mortgage = MortgageInDB(
        lender_id       = mortgage_data.lender_id,
        debtor_id       = mortgage_data.debtor_id,
        agent_id        = mortgage_data.agent_id,
        matricula_id    = mortgage_data.matricula_id,
        start_date      = mortgage_data.start_date,
        initial_balance = mortgage_data.initial_balance,
        interest_rate   = mortgage_data.interest_rate,
        current_balance = mortgage_data.initial_balance,
        last_update     = local_timestamp_str,
        monthly_payment = mortgage_data.initial_balance * mortgage_data.interest_rate / 100,
        mortgage_status = "active"  # default status to active when mortgage is created
    )

    # Log successful mortgage creation
    log_entry = LogsInDb(
        action      = "Mortgage Created",
        timestamp   = local_timestamp_str,
        message     = f"Mortgage created for lender {lender.username}, debtor {debtor.username}, property {property.matricula_id}",
        user_id     = decoded_token.get("id")
    )
    db.add(log_entry)

    db.add(new_mortgage)
    db.commit()
    db.refresh(new_mortgage)

    new_reg = RegsInDb(
        mortgage_id     = new_mortgage.id,
        lender_id       = lender.id_number,
        debtor_id       = debtor.id_number,
        date            = mortgage_data.start_date,
        concept         = "Primera cuota, debito automatico",
        amount          = new_mortgage.monthly_payment,
        penalty         = 0,
        min_payment     = new_mortgage.monthly_payment,
        limit_date      = (mortgage_data.start_date + timedelta(days=5)),
        to_main_balance = 0,
        payment_status  = "approved",
        comment         = "System"
    )

    db.add(new_reg)
    property.prop_status = "loaned"
    db.commit()
    return {"message": "Mortgage and initial payment registered successfully"}

    


@router.get("/mortgages/debtor/{debtor_id}") #LOGS
def get_mortgages_by_debtor(debtor_id: str, db: Session = Depends(get_db)):
    debtor = db.query(UserInDB).filter(UserInDB.id_number == debtor_id).first()
    
    if debtor is None:
        # Log user not found
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"User not found with ID: {debtor_id}",
            user_id     = debtor_id
        )
        db.add(log_entry)
        db.commit()
        return {"message": "No existe usuario con el ID en referencia"}

    # Log successful retrieval of mortgages
    log_entry = LogsInDb(
        action      = "User Accessed Mortgages Component",
        timestamp   = local_timestamp_str,
        message     = f"Mortgages retrieved for debtor with ID: {debtor_id}",
        user_id     = debtor_id
    )
    db.add(log_entry)
    db.commit()

    mortgages = db.query(MortgageInDB).filter(MortgageInDB.debtor_id == debtor_id).all()

    if not mortgages:
        return {"message": "No tienes hipotecas como deudor"}
    else:
        mortgage_info = []

        for mortgage in mortgages:
            most_recent_reg = db.query(RegsInDb).filter(RegsInDb.mortgage_id == mortgage.id).order_by(desc(RegsInDb.id)).first()
            if most_recent_reg:
                mortgage_data = {**mortgage.__dict__, "comprobante": None, "concept": None, "limit_date": None, "penalty": None, "payment_status": None, "amount": None, "to_main_balance": None, "date": None, "lender_id": None, "min_payment": None, "id": None, "comment": None}
                mortgage_data.update({**most_recent_reg.__dict__, "last_registers_mortgage_id": most_recent_reg.mortgage_id})
                mortgage_info.append(mortgage_data)

        # Check for pending payments
        payments_pendings = db.query(RegsInDb).filter(RegsInDb.payment_status == "pending", RegsInDb.debtor_id == debtor_id).count()

        return {"mortgage_info": mortgage_info, "payments_pendings": payments_pendings}



@router.get("/mortgages/lender/{lender_id}") #LOGS
def get_mortgages_by_lender(lender_id: str, db: Session = Depends(get_db)):
    lender = db.query(UserInDB).filter(UserInDB.id_number == lender_id).first()
    
    if lender is None:
        # Log lender not found
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"No user found with the provided lender ID: {lender_id}",
            user_id     = lender_id
        )
        db.add(log_entry)
        db.commit()
        return {"message": "No user found with the provided lender ID"}

    # Log successful retrieval of investments in mortgages
    log_entry = LogsInDb(
        action      = "Investment Component Accessed",
        timestamp   = local_timestamp_str,
        message     = f"Investments retrieved for lender with ID: {lender_id}",
        user_id     = lender_id
    )
    db.add(log_entry) 
    db.commit()

    mortgages   = db.query(MortgageInDB).filter(MortgageInDB.lender_id == lender_id).all()
    paid        = []
    regs        = db.query(RegsInDb).filter(RegsInDb.lender_id == lender_id).all()
    
    for reg in regs:
        if reg.payment_status == "approved":
            paid.append(reg)

    if not mortgages:
        return {"message": "No tienes inversiones en hipotecas aún"}
    else:
        result = [mortgage.__dict__ for mortgage in mortgages]
        return {"results" :result, "paid" : paid}



@router.get("/admin_panel/mortgages/") #LOGS #TOKE-ROLE ADMIN
async def get_all_mortgages(db: Session = Depends(get_db), token: str = Header(None)):
    if token:
        decoded_token   = decode_jwt(token)
        role            = decoded_token.get("role")
        if role == "admin":
            mortgages = db.query(MortgageInDB).all()
            mortgage_info = []
            for mortgage in mortgages:
                mortgage_info.append({
                    "id"                : mortgage.id,
                    "debtor_id"         : mortgage.debtor_id,
                    "current_balance"   : mortgage.current_balance,
                    "interest_rate"     : mortgage.interest_rate,
                    "mortgage_status"   : mortgage.mortgage_status
                })

            # Log successful retrieval of all mortgages
            log_entry = LogsInDb(
                action      = "Mortgages Component Accessed",
                timestamp   = local_timestamp_str,
                message     = "All mortgages retrieved by admin",
                user_id     = decoded_token.get("id")
            )
            db.add(log_entry)
            db.commit()

            return mortgage_info
        else:
            # Log unauthorized access attempt
            log_entry = LogsInDb(
                action      = "User Alert",
                timestamp   = local_timestamp_str,
                message     = "Unauthorized access attempt to view all mortgages (Insufficient permissions)",
                user_id     = decoded_token.get("id")
            )
            db.add(log_entry)
            db.commit()

            raise HTTPException(status_code=403, detail="No tienes permiso de ver esta informacion")
    else:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to view all mortgages (Token not provided)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=401, detail="Token not provided")

@router.get("/mortgages/debtor/{debtor_id}")  # LOGS
def get_mortgages_by_debtor(debtor_id: str, db: Session = Depends(get_db)):
    debtor = db.query(UserInDB).filter(UserInDB.id_number == debtor_id).first()

    if debtor is None:
        # Log user not found
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"User not found with ID: {debtor_id}",
            user_id=debtor_id
        )
        db.add(log_entry)
        db.commit()
        return {"message": "No existe usuario con el ID en referencia"}

    # Log successful retrieval of mortgages
    log_entry = LogsInDb(
        action="User Accessed Mortgages Component",
        timestamp=local_timestamp_str,
        message=f"Mortgages retrieved for debtor with ID: {debtor_id}",
        user_id=debtor_id
    )
    db.add(log_entry)
    db.commit()

    mortgages = db.query(MortgageInDB).filter(MortgageInDB.debtor_id == debtor_id).all()

    if not mortgages:
        return {"message": "No tienes hipotecas como deudor"}
    else:
        result = [mortgage.__dict__ for mortgage in mortgages]
        return result


@router.get("/mortgage_detail/{debtor_id}")  # LOGS #TOKEN ADMIN ONLY
def get_mortgage_details_by_debtor(debtor_id: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized access attempt to retrieve mortgage details (Token not provided)",
            user_id=None  # Since the token isn't provided, set it to None
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=401, detail="Token not provided")

    # Decode the token and verify the user's role
    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_pk_from_token = decoded_token.get("id")

    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message="Unauthorized access attempt to retrieve mortgage details (Insufficient permissions)",
            user_id=user_pk_from_token  # Use the primary key ID from the token
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para ver estos detalles")

    debtor = db.query(UserInDB).filter(UserInDB.id_number == debtor_id).first()

    if debtor is None:
        # Log user not found
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"User not found with ID: {debtor_id}",
            user_id=user_pk_from_token  # Use the primary key ID from the token
        )
        db.add(log_entry)
        db.commit()

        return {"message": "No existe usuario con el ID en referencia"}

    # Log successful retrieval of mortgages
    log_entry = LogsInDb(
        action="Admin Accessed Mortgages Component",
        timestamp=local_timestamp_str,
        message=f"Mortgages retrieved for debtor with ID: {debtor_id} (by admin)",
        user_id=user_pk_from_token  # Use the primary key ID from the token
    )
    db.add(log_entry)
    db.commit()

    mortgage_info = []
    mortgages = db.query(MortgageInDB).filter(MortgageInDB.debtor_id == debtor_id).all()

    for mortgage in mortgages:
        most_recent_reg = db.query(RegsInDb).filter(RegsInDb.mortgage_id == mortgage.id).order_by(desc(RegsInDb.id)).first()
        if most_recent_reg:
            mortgage_data = {**mortgage.__dict__, "comprobante": None, "concept": None, "limit_date": None, "penalty": None, "payment_status": None, "amount": None, "to_main_balance": None, "date": None, "lender_id": None, "min_payment": None, "id": None, "comment": None}
            mortgage_data.update({**most_recent_reg.__dict__, "last_registers_mortgage_id": most_recent_reg.mortgage_id})
            mortgage_info.append(mortgage_data)

    payments_pendings = 0

    regs = db.query(RegsInDb).filter(RegsInDb.payment_status == "pending", RegsInDb.debtor_id == debtor_id).all()

    if regs:
        payments_pendings = len(regs)

    return {"mortgage_info": mortgage_info, "payments_pendings": payments_pendings}


