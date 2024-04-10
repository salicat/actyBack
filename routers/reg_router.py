from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Header, Form
from datetime import date, datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import RegsInDb, UserInDB, MortgageInDB, PenaltyInDB, LogsInDb, File
from models.reg_models import RegCreate, SystemReg, RegsUpDate
import os
import jwt
import shutil
import json


utc_now                 = datetime.now(timezone.utc)
utc_offset              = timedelta(hours=-5)
local_now               = utc_now + utc_offset
local_timestamp_str     = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

SECRET_KEY                  = "8/8"
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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

router = APIRouter()

def reg_to_dict(reg):
        return {
            "id"                : reg.id,
            "mortgage_id"       : reg.mortgage_id,
            "lender_id"         : reg.lender_id,
            "debtor_id"         : reg.debtor_id,
            "date"              : reg.date,
            "concept"           : reg.concept,
            "amount"            : reg.amount,
            "penalty"           : reg.penalty,
            "min_payment"       : reg.min_payment,
            "limit_date"        : reg.limit_date,
            "to_main_balance"   : reg.to_main_balance,
            "comprobante"       : reg.comprobante,
            "payment_status"    : reg.payment_status,
            "comment"           : reg.comment,
        }
translate_status = {
    "approved"  : "aprobado",
    "rejected"  : "rechazado",
    "pending"   : "pendiente"
}



@router.post("/mortgage_payment/register/")  #LOGS
async def register_mortgage_payment(
    payment_receipt: UploadFile = FastAPIFile(...),
    reg_data: str = Form(...),
    db: Session = Depends(get_db), 
    token: str = Header(None)):

    print("Received reg_data:", reg_data)  # Print reg_data as received
    reg_data_dict = json.loads(reg_data)
    print("Parsed reg_data_dict:", reg_data_dict) 
    
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to register mortgage payment (Token not provided)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    user_id_from_token = decoded_token.get("id")

    # Fetch mortgage details
    mortgage_id = reg_data_dict['mortgage_id']
    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == mortgage_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="Mortgage not found")

    upload_folder = './uploads'
    os.makedirs(upload_folder, exist_ok=True)
    
    payment_receipt_filename = f"{mortgage.id}_receipt_{payment_receipt.filename}"
    payment_receipt_location = f"{upload_folder}/{payment_receipt_filename}"
    with open(payment_receipt_location, "wb") as buffer:
        shutil.copyfileobj(payment_receipt.file, buffer)
    
    save_file_to_db(db, "mortgage_payment", mortgage.id, "payment_receipt", payment_receipt_location)

    log_entry = LogsInDb(
        action      = "Payment Receipt Uploaded",
        timestamp   = datetime.now(),
        message     = f"Payment receipt uploaded for mortgage ID: {mortgage.id}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    # Use the last system-generated register to get some default values
    last_system_register = (
    db.query(RegsInDb)
    .filter(RegsInDb.mortgage_id == reg_data_dict['mortgage_id'], RegsInDb.comment == "System")  # Use reg_data_dict
    .order_by(RegsInDb.date.desc())
    .first()
    )
  
    # Set default values based on the last system-generated register
    debtor_id   = last_system_register.debtor_id if last_system_register else reg_data_dict['debtor_id']
    min_payment = last_system_register.min_payment if last_system_register else reg_data_dict['min_payment']
    limit_date  = last_system_register.limit_date if last_system_register else reg_data_dict['limit_date']

    # Create a new mortgage payment register
    new_register = RegsInDb(
        mortgage_id     = reg_data_dict['mortgage_id'],
        lender_id       = mortgage.lender_id,
        debtor_id       = debtor_id,
        date            = reg_data_dict['payment_date'],  # Make sure the key matches what you send from the frontend
        concept         = "Pago reportado por usuario",
        amount          = reg_data_dict['paid'],  # Make sure the key matches what you send from the frontend
        penalty         = 0,
        min_payment     = min_payment,
        limit_date      = limit_date,
        to_main_balance = 0,
        comprobante     = payment_receipt_location,  # Already correctly set above
        payment_status  = "pending",
        comment         = "debtor"
    )

    # Log successful mortgage payment registration
    log_entry = LogsInDb(
    action      = "Mortgage Payment Registered",
    timestamp   = datetime.now(),
    message     = f"Mortgage payment registered for mortgage ID: {reg_data_dict['mortgage_id']}",  # Corrected access
    user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    # Commit the changes to the database
    db.add(new_register)
    db.commit()

    return {"message": "Pago reportado con exito"}



@router.get("/pending_regs/{status}")  #LOGS TOKEN
def pending_regs(status: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to get pending registers (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")


    # Admin permission check
    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to get pending registers (Admin permission required)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Admin permission required")

    # Validate status parameter
    if status not in ["approved", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail=f"Invalid status value: {status}")

    regs = db.query(RegsInDb).filter(RegsInDb.payment_status == status).all()
    records = [{
        "id"                : reg.id,
        "mortgage_id"       : reg.mortgage_id,
        "lender_id"         : reg.lender_id,
        "debtor_id"         : reg.debtor_id,
        "date"              : reg.date,
        "concept"           : reg.concept,
        "amount"            : reg.amount,
        "penalty"           : reg.penalty,
        "min_payment"       : reg.min_payment,
        "limit_date"        : reg.limit_date,
        "to_main_balance"   : reg.to_main_balance,
        "comprobante"       : reg.comprobante,
        "payment_status"    : reg.payment_status,
        "comment"           : reg.comment,
            } for reg in regs]


    if not regs:
        return {"records": []}  # Return an empty list if there are no records

    return {"records": records}

 
@router.get("/get_regs/{debtor_id}") #TOKEN LOGS
async def get_regs(debtor_id: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to retrieve user records (Token not provided)",
            user_id     = None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")
    user_id_from_token  = decoded_token.get("id")

    if role_from_token != "admin" and user_id_from_token != str(debtor_id):
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = "Unauthorized access attempt to retrieve user records (Insufficient permissions)",
            user_id     = user_id_from_token
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estos registros")

    all_regs    = db.query(RegsInDb).filter(RegsInDb.debtor_id == debtor_id).order_by(RegsInDb.date).all()
    user        = db.query(UserInDB).filter(UserInDB.id_number == debtor_id).first()
    if not user:
        return {"message": "Usuario no existe en la base de datos, revisa los valores ingresados"}
    regs = []

    for record in all_regs:
        regs.append({ 
            "payment_date"      : record.date,
            "concept"           : record.concept,
            "amount"            : record.amount,
            "penalty"           : record.penalty,
            "min_payment"       : record.min_payment,
            "limit_date"        : record.limit_date,
            "to_main_balance"   : record.to_main_balance,
            "status"            : record.payment_status,  
            "id"                : record.id
        })

    if not regs:
        if user and not all_regs:
            return {"message": "El usuario aun no registra movimientos"}
        else:
            return {"message": f"No hay registros para el deudor con ID {debtor_id}"}

    return {"regs": regs}



@router.post("/closing_date/")
async def generate_system_payment(reg_data: SystemReg, db: Session = Depends(get_db), token: str = Header(None)):

    decoded_token = None  # Initialize decoded_token outside the if block

    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")
    user_id_from_token = decoded_token.get("id")

    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para generar pagos automáticos")

    debtor_id = reg_data.debtor_id

    # Check if the router was already used this month or if there is a missing month
    last_system_register = (
        db.query(RegsInDb)
        .filter(RegsInDb.debtor_id == debtor_id, RegsInDb.comment == "System")
        .order_by(RegsInDb.date.desc())
        .first()
    )

    if last_system_register:
        last_month = reg_data.date.month - 1 if reg_data.date.month > 1 else 12

        if last_system_register.date.month == reg_data.date.month:
            raise HTTPException(status_code=400, detail="El proceso ya se ejecutó para este mes")
        elif last_system_register.date.month != last_month:
            raise HTTPException(status_code=400, detail="Mes faltante en registros")

    last_register = (
        db.query(RegsInDb)
        .filter(RegsInDb.debtor_id == debtor_id)
        .order_by(RegsInDb.date.desc())
        .first()
    )

    if not last_register:
        raise HTTPException(status_code=404, detail="No se encontraron registros para el deudor")

    # Check if the last register has pending payment status
    if last_register.payment_status.lower() != "approved":
        raise HTTPException(
            status_code=400, detail="El último registro no tiene un pago aprobado. Verifique antes de proceder."
        )

    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == last_register.mortgage_id).first()

    # Check if the last register is system-generated and has no amount reported
    if last_register.comment.lower() == "system" and last_register.amount == 0:
        # Check if there is a penalty rate set for the closing month
        penalty_rate = (
            db.query(PenaltyInDB).filter(PenaltyInDB.start_date <= reg_data.date, PenaltyInDB.end_date >= reg_data.date).first()
        )

        if not penalty_rate:
            raise HTTPException(
                status_code=400,
                detail="No hay un interés de mora fijado para el mes actual. "
                       "Asegúrese de configurar la tasa de interés de mora antes de continuar."
            )

        penalty_amount = (mortgage.current_balance * penalty_rate.penalty_rate) / 100
        penalty_description = f"Intereses de mora generados ({penalty_rate.penalty_rate}%) "
        mortgage.mortgage_status = "debt_pending"

    else:
        # Check if the last register was a payment reported by the user
        if last_register.concept.lower() == "pago reportado por usuario":
            # Calculate if the payment was on time
            if last_register.amount >= last_register.min_payment:
                # The payment was on time, no penalty needed
                penalty_amount = 0
                penalty_description = ""
            else:
                # Check if there is a penalty rate set for the closing month
                penalty_rate = (
                    db.query(PenaltyInDB)
                    .filter(
                        PenaltyInDB.start_date <= reg_data.date.replace(day=1),
                        PenaltyInDB.end_date >= reg_data.date.replace(day=31)
                    )
                    .first()
                )

                if not penalty_rate:
                    raise HTTPException(
                        status_code=400,
                        detail="No hay un interés de mora fijado para el mes actual. "
                               "Asegúrese de configurar la tasa de interés de mora antes de continuar."
                    )

                penalty_days = (last_register.date - last_register.limit_date).days
                penalty_amount = ((last_register.min_payment * penalty_rate.penalty_rate / 100) / 30) * penalty_days
                penalty_description = f"Intereses de mora generados ({penalty_rate.penalty_rate}%) por {penalty_days} días"
        else:
            # Check if there is a penalty rate set for the closing month
            penalty_rate = (
                db.query(PenaltyInDB)
                .filter(
                    PenaltyInDB.start_date <= reg_data.date.replace(day=1),
                    PenaltyInDB.end_date >= reg_data.date.replace(day=30)
                )
                .first()
            )

            if not penalty_rate:
                raise HTTPException(
                    status_code=400,
                    detail="No hay un interés de mora fijado para el mes actual. "
                           "Asegúrese de configurar la tasa de interés de mora antes de continuar."
                )

            penalty_days = (last_register.date - last_register.limit_date).days
            penalty_amount = ((last_register.min_payment * penalty_rate.penalty_rate / 100) / 30) * penalty_days
            penalty_description = f"Intereses de mora generados ({penalty_rate.penalty_rate}%) por {penalty_days} días"

    # Calculate current month min_payment
    if not mortgage:
        raise HTTPException(status_code=404, detail="No se encontró la hipoteca asociada al último registro")

    min_payment = (mortgage.current_balance * mortgage.interest_rate / 100) + penalty_amount

    # Check if there is any amount reported by the user
    if last_register.amount > 0:
        # Check if there is any remaining after discounts
        remaining = last_register.amount - min_payment - penalty_amount
        if remaining > 0:
            # If the remaining is more than 5% of the mortgage current_balance, update the mortgage
            if remaining > (0.05 * mortgage.current_balance):
                mortgage.current_balance -= remaining
                last_register.to_main_balance = remaining
            else:
                # Update the min_payment for the next month
                min_payment += remaining

    # Commit the changes to the mortgage before calculating the next min_payment
    db.commit()

    # Calculate current month min_payment after updating the mortgage.current_balance
    min_payment = (mortgage.current_balance * mortgage.interest_rate / 100) + penalty_amount

    # Create a new system payment register
    new_register = RegsInDb(
        mortgage_id=last_register.mortgage_id,
        lender_id=last_register.lender_id,
        debtor_id=debtor_id,
        date=reg_data.date,
        concept=f"Cobro generado por sistema ({penalty_description})",
        amount=0,
        penalty=penalty_amount,
        min_payment=min_payment,
        limit_date=reg_data.date.replace(day=5) + relativedelta(months=1),
        to_main_balance=0,
        payment_status="approved",
        comment="System",
    )

    # Update mortgage last_update date
    mortgage.last_update = reg_data.date

    # Log successful system payment generation
    log_entry = LogsInDb(
        action="System Payment Generated",
        timestamp=local_timestamp_str,
        message=f"Sistema generó un cobro para el deudor {debtor_id}",
        user_id=user_id_from_token,
    )
    db.add(log_entry)

    # Commit the changes to the database
    db.add(new_register)
    db.commit()

    return {"message": "Cobro generado por sistema exitosamente"}






@router.get("/get_reg/{reg_id}") #LOGS TOKEN ADMIN ONLY
def get_reg(reg_id: int, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to get register (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    # Admin permission check
    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to get register (Admin permission required)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Admin permission required")
    
    

    # Query the database for the register
    reg = db.query(RegsInDb).filter(RegsInDb.id == reg_id).first()

        # Log the SQL query being executed
    print(db.query(RegsInDb).filter(RegsInDb.id == reg_id).statement.compile(compile_kwargs={"literal_binds": True}))

    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    return reg_to_dict(reg)


@router.put("/update_reg/")
def update_register_status(reg_update: RegsUpDate, db: Session = Depends(get_db), token: str = Header(None)):

    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to update register (Token not provided)",
            user_id=None
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    # Admin permission check
    if role_from_token != "admin":
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to update register (Admin permission required)",
            user_id=decoded_token.get("id")
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Admin permission required")

    # Query the database for the register
    reg = db.query(RegsInDb).filter(RegsInDb.id == reg_update.reg_id).first()

    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    # Update payment_status to new_status
    reg.payment_status = reg_update.new_status

    # If the new status is "approved", update MortgageInDB.last_update
    if reg_update.new_status.lower() == "approved":
        mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == reg.mortgage_id).first()
        if mortgage:
            mortgage.last_update = reg.date

    # Log the update operation
    log_entry = LogsInDb(
        action="Register Status Updated",
        timestamp=local_timestamp_str,
        message=f"Registro {reg_update.reg_id} actualizado a estado: {reg_update.new_status}",
        user_id=decoded_token.get("id")
    )
    db.add(log_entry)
    db.commit()

    return {"message": f"Registro {reg_update.reg_id} actualizado exitosamente"}

    
@router.delete("/registers/delete/{register_id}")
def delete_register(register_id: int, db: Session = Depends(get_db)):
    existing_register = db.query(RegsInDb).filter(RegsInDb.id == register_id).first()
    if not existing_register:
        raise HTTPException(status_code=404, detail="Register not found")
    db.delete(existing_register)
    db.commit()
    return {"message": "Register deleted successfully"}
