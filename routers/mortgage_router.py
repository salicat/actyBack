from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import desc
from db.db_connection import get_db
from db.all_db import MortgageInDB, UserInDB, PropInDB, RegsInDb, File, LogsInDb, LoanProgress
from models.mortgage_models import MortgageCreate
from datetime import timedelta, date, datetime
import jwt

utc_now = datetime.utcnow() 
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
def create_mortgage(mortgage_data   : MortgageCreate, 
                    db              : Session = Depends(get_db), 
                    token           : str = Header(None)): 
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

    if role_from_token != "admin": # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized attempt to create mortgage (Insufficient permissions)",
            user_id     = None  
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(status_code=403, detail="No tienes permiso para crear hipotecas")

    lender = db.query(UserInDB).filter(UserInDB.id_number == mortgage_data.lender_id).first()
    debtor = db.query(UserInDB).filter(UserInDB.id_number == mortgage_data.debtor_id).first()

    if not lender or not debtor: # Log invalid lender or debtor access attempt
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

    if not debtor_properties: # Log user with no registered properties access attempt
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

    if property.prop_status != "process":
        # Log unauthorized access attempt to create mortgage with an unavailable property
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Inmueble no disponible para hipoteca",
            user_id     = decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()

        raise HTTPException(
            status_code = 400, 
            detail      = "Inmueble no disponible para hipoteca"
        )

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
                # Start with a clean copy of mortgage.__dict__ excluding 'id'
                mortgage_data = {k: v for k, v in mortgage.__dict__.items() if k != 'id'}

                # Update with most_recent_reg.__dict__ excluding 'id'
                reg_data = {k: v for k, v in most_recent_reg.__dict__.items() if k != 'id'}
                mortgage_data.update(reg_data)

                # Ensure 'id' is explicitly set to mortgage's ID, not overridden
                mortgage_data['id'] = mortgage.id
                mortgage_data['last_registers_mortgage_id'] = most_recent_reg.mortgage_id

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
                if mortgage.mortgage_status == 'loaned':    
                    mortgage_info.append({
                        "id"                : mortgage.id,
                        "debtor_id"         : mortgage.debtor_id,
                        "current_balance"   : mortgage.current_balance,
                        "interest_rate"     : mortgage.interest_rate,
                        "mortgage_status"   : mortgage.mortgage_status
                    })
            props = db.query(MortgageInDB).all()
            mort_to_process = []
            for prop in props:
                if prop.mortgage_stage != None:
                    debtor = db.query(UserInDB).filter(UserInDB.id_number == prop.debtor_id).first()
                    debtor_username = debtor.username if debtor else "Unknown"
                    mort_to_process.append({
                        "property_pk"   : prop.id,
                        "matricula_id"  : prop.matricula_id,
                        "deudor"        : debtor_username  
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

            return {"mortgage_info" : mortgage_info, "mort_to_process" : mort_to_process}
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


@router.get("/process_mortgages/{property_id}")
def process_mortgages(property_id: int, db: Session = Depends(get_db), token: str = Header(None)):

    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")
    
    decoded_token = decode_jwt(token)
    role = decoded_token.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Access denied, admin role required")
    
    # Query for the property that is in the "selected" status
    property = db.query(MortgageInDB).filter(MortgageInDB.id == property_id).first()
    if not property:
        raise HTTPException(status_code=404, detail="Selected property not found")

    # Query for the latest loan progress related to the selected property with the specific status
    loan_progress = db.query(LoanProgress).filter(
        LoanProgress.property_id == property_id, 
        LoanProgress.status == "Tramite de hipoteca solicitado"
    ).order_by(LoanProgress.date.desc()).first()

    if not loan_progress:
        raise HTTPException(status_code=404, detail="Loan progress for the selected property not found")

    # Query for debtor and lender information based on the found records
    debtor = db.query(UserInDB).filter(UserInDB.id_number == property.debtor_id).first()
    lender = db.query(UserInDB).filter(UserInDB.id_number == loan_progress.lender_id).first()
    if not debtor or not lender:
        raise HTTPException(status_code=404, detail="User information not found")

    return {
        "deudor": {
            "id_number": debtor.id_number,
            "username": debtor.username,
            "email": debtor.email
        },
        "inversionista": {
            "id_number": lender.id_number,
            "username": lender.username,
            "email": lender.email
        }
    }


@router.get("/gestion_hipotecas/{property_id}")
async def gestion_hipotecas(property_id: int, db: Session = Depends(get_db), token: str = Header(None)):
    decoded_token   = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    
    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == property_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="Mortgage not found")
    
    property = db.query(PropInDB).filter(PropInDB.matricula_id == mortgage.matricula_id).first()
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    def user_info_with_documents(user):
        user_files = db.query(File).filter(File.entity_id == user.id).all()
        documents_status = {
            "cedula_front": None,
            "cedula_back": None,
            "tax_id_file": None,
            "bank_certification": None,
        }

        for file in user_files:
            if file.file_type in documents_status:
                documents_status[file.file_type] = {"uploaded": True, "path": file.file_location}

        return {
            "username"          : user.username,
            "email"             : user.email,
            "phone"             : user.phone,
            "agente"            : user.added_by, 
            "legal_address"     : user.legal_address,
            "user_city"         : user.user_city,
            "user_department"   : user.user_department,
            "id_number"         : user.id_number,
            "tax_id"            : user.tax_id,
            "bank_name"         : user.bank_name,
            "account_type"      : user.account_type,
            "account_number"    : user.account_number,
            "documents": [
                {"name": "Cedula cara frontal", "key": "cedula_front", "uploaded": documents_status["cedula_front"] is not None, "path": documents_status["cedula_front"]["path"] if documents_status["cedula_front"] else None},
                {"name": "Cedula cara posterior", "key": "cedula_back", "uploaded": documents_status["cedula_back"] is not None, "path": documents_status["cedula_back"]["path"] if documents_status["cedula_back"] else None},
                {"name": "Rut", "key": "tax_id_file", "uploaded": documents_status["tax_id_file"] is not None, "path": documents_status["tax_id_file"]["path"] if documents_status["tax_id_file"] else None},
                {"name": "Certificacion bancaria", "key": "bank_certification", "uploaded": documents_status["bank_certification"] is not None, "path": documents_status["bank_certification"]["path"] if documents_status["bank_certification"] else None},
            ]
        }

    debtor = db.query(UserInDB).filter(UserInDB.id_number == mortgage.debtor_id).first()
    lender = db.query(UserInDB).filter(UserInDB.id_number == mortgage.lender_id).first()
    
    if not debtor or not lender:
        raise HTTPException(status_code=404, detail="Debtor or Lender not found")

    debtor_info = user_info_with_documents(debtor)
    lender_info = user_info_with_documents(lender)

    return {
        "deudor"        : debtor_info,
        "inversionista" : lender_info,
        "inmueble"      : property,
        "hipoteca"      : mortgage
    }
