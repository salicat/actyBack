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
            "paid"              : reg.paid,
            "concept"           : reg.concept,
            "amount"            : reg.amount,
            "penalty"           : reg.penalty,
            "penalty_days"      : reg.penalty_days, 
            "min_payment"       : reg.min_payment,
            "limit_date"        : reg.limit_date,
            "to_main_balance"   : reg.to_main_balance,
            "comprobante"       : reg.comprobante,
            "payment_status"    : reg.payment_status,
            "comment"           : reg.comment,
            "payment_type"      : reg.payment_type
        }
translate_status = {
    "approved"  : "aprobado",
    "rejected"  : "rechazado",
    "pending"   : "pendiente"
}



@router.post("/mortgage_payment/register/")  # LOGS
async def register_mortgage_payment(
    payment_receipt : UploadFile    = FastAPIFile(None),  # Archivo ahora es opcional
    reg_data        : str           = Form(...),
    db              : Session       = Depends(get_db), 
    token           : str           = Header(None)
):
    # Convertir reg_data de JSON a diccionario
    reg_data_dict = json.loads(reg_data)

    decoded_token = decode_jwt(token)
    user_id_from_token = decoded_token.get("id")

    paid_amount = reg_data_dict['paid']
    payment_date = payment_date  # tras parsearlo a datetime.date

    duplicate = (
        db.query(RegsInDb)
        .filter(
            RegsInDb.mortgage_id   == mortgage_id,
            RegsInDb.debtor_id     == debtor_id,
            RegsInDb.date          == payment_date,
            RegsInDb.paid          == paid_amount,
        )
        .first()
    )
    if duplicate:
        raise HTTPException( status_code=400, detail="Ya existe un pago registrado con esos mismos datos.")
    
    
    # Buscar hipoteca en la base de datos
    mortgage_id = reg_data_dict['mortgage_id']
    mortgage    = db.query(MortgageInDB).filter(MortgageInDB.id == mortgage_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="Mortgage not found")

    # Subir comprobante si se proporciona
    payment_receipt_location = None
    payment_type = "PSE"  # Por defecto, si no se proporciona archivo
    if payment_receipt:
        upload_folder = './uploads'
        os.makedirs(upload_folder, exist_ok=True) 
        payment_receipt_filename = f"{mortgage.id}_receipt_{payment_receipt.filename}"
        payment_receipt_location = f"{upload_folder}/{payment_receipt_filename}"
        with open(payment_receipt_location, "wb") as buffer:
            shutil.copyfileobj(payment_receipt.file, buffer)
        save_file_to_db(db, "mortgage_payment", mortgage.id, "payment_receipt", payment_receipt_location)
        payment_type = "consignacion bancaria"

    # Log del recibo de pago
    log_entry = LogsInDb(
        action      = "Payment Receipt Uploaded" if payment_receipt else "Payment Reported (PSE)",
        timestamp   = local_timestamp_str,
        message     = f"Payment {payment_type} reported for mortgage ID: {mortgage.id}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    # Obtener el último registro generado automáticamente por el sistema
    last_system_register = (db.query(RegsInDb).filter(RegsInDb.mortgage_id == mortgage_id, RegsInDb.comment == "System").order_by(RegsInDb.date.desc()).first())

    # Valores predeterminados
    debtor_id   = last_system_register.debtor_id if last_system_register else reg_data_dict['debtor_id']
    min_payment = last_system_register.min_payment if last_system_register else reg_data_dict['min_payment']
    limit_date  = last_system_register.limit_date if last_system_register else reg_data_dict['limit_date']

    # Calcular mora y determinar tipo de pago
    # Asegúrate de que payment_date y limit_date sean de tipo datetime.date
    payment_date = reg_data_dict['payment_date']
    if isinstance(payment_date, str):  # Si es cadena, conviértelo a datetime.date
        payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()

    limit_date = limit_date  # Aquí limit_date ya debe ser de tipo datetime.date
    if isinstance(limit_date, str):  # Si es cadena, conviértelo a datetime.date
        limit_date = datetime.strptime(limit_date, '%Y-%m-%d').date()

    # Calcular mora y determinar tipo de pago
    mora_days = (payment_date - limit_date).days if payment_date > limit_date else 0
    ext = "extemporaneo" if mora_days > 0 else "normal"

    # Crear un nuevo registro de pago
    new_register = RegsInDb(
        mortgage_id     = mortgage_id,
        lender_id       = mortgage.lender_id,
        debtor_id       = debtor_id,
        date            = payment_date,
        paid            = reg_data_dict['paid'],
        concept         = f"Pago {ext} reportado por usuario",
        amount          = 0,
        penalty         = 0,
        penalty_days    = mora_days,
        min_payment     = min_payment,
        limit_date      = limit_date,
        to_main_balance = 0,
        comprobante     = payment_receipt_location,
        payment_status  = "pending",
        comment         = f"Pagado con {mora_days} días en mora" if mora_days > 0 else "Pago en fecha",
        payment_type    = payment_type
    )

    # Registrar la acción en logs
    log_entry = LogsInDb(
        action      = "Mortgage Payment Registered",
        timestamp   = local_timestamp_str,
        message     = f"Mortgage payment registered for mortgage ID: {mortgage_id}",
        user_id     = user_id_from_token
    )
    db.add(log_entry)
    db.commit()

    # Guardar el nuevo registro
    db.add(new_register)
    db.commit()

    # Mensaje final para el usuario
    if mora_days > 0:
        message = (
            f"Su pago ha sido reportado como extemporáneo con {mora_days} días en mora. "
            f"Por ser un reporte manual ({payment_type}), será revisado y formalizado en los próximos días."
        )
    else:
        message = (
            f"Tu pago ha sido reportado. "
            f"Por ser un reporte manual ({payment_type}), será revisado y formalizado en los próximos días."
        )

    return {"message": message}



@router.get("/pending_regs/{status}")  #LOGS TOKEN
def pending_regs(status: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        # Log unauthorized access attempt
        log_entry = LogsInDb(
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"Unauthorized access attempt to get pending registers (Token not provided)",
            user_id     = None
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
            action      = "User Alert",
            timestamp   = local_timestamp_str,
            message     = f"Unauthorized access attempt to get pending registers (Admin permission required)",
            user_id     = decoded_token.get("id")
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
        "paid"              : reg.paid,
        "concept"           : reg.concept,
        "amount"            : reg.amount,
        "penalty"           : reg.penalty,
        "penalty_days"      : reg.penalty_days,
        "min_payment"       : reg.min_payment,
        "limit_date"        : reg.limit_date,
        "to_main_balance"   : reg.to_main_balance,
        "comprobante"       : reg.comprobante,
        "payment_status"    : reg.payment_status,
        "comment"           : reg.comment,
        "payment_type"      : reg.payment_type
            } for reg in regs]


    if not regs:
        return {"records": []}  # Return an empty list if there are no records

    return {"records": records}

 
@router.get("/get_regs/{debtor_id}") #TOKEN LOGS
async def get_regs(debtor_id: str, db: Session = Depends(get_db), token: str = Header(None)):

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

    debtor_id = debtor_id.strip()
   
    user        = db.query(UserInDB).filter(UserInDB.id_number == debtor_id).first()
    all_regs    = db.query(RegsInDb).filter(RegsInDb.debtor_id == debtor_id).order_by(RegsInDb.date).all()
    
    if not user:
        return {"message": "Usuario no existe en la base de datos, revisa los valores ingresados"}
    regs = []
    mortgages = db.query(MortgageInDB).filter(MortgageInDB.debtor_id == debtor_id).all()
    
    mort = []
    for mor in mortgages:
        if mor.debtor_id == debtor_id:
            mort.append(mor)
 
    for record in all_regs:
        regs.append({  
            "date"              : record.date,
            "concept"           : record.concept,
            "paid"              : record.paid,
            "amount"            : record.amount,
            "penalty"           : record.penalty,
            "penalty_days"      : record.penalty_days,
            "min_payment"       : record.min_payment,
            "limit_date"        : record.limit_date,
            "to_main_balance"   : record.to_main_balance,
            "comprobante"       : record.comprobante,
            "status"            : record.payment_status,  
            "payment_type"      : record.payment_type,
            "comments"          : record.comment,
            "id"                : record.id
        })

    if not regs:
        regs = [{"message": "El usuario aún no registra movimientos"}]

    if not mort:
        mort = [{"message": f"No hay hipotecas para el deudor con ID {debtor_id}"}]

    return {
        "regs": regs,
        "mort": mort
    }


@router.post("/closing_date/")
async def generate_system_payment(
    reg_data: SystemReg, db: Session = Depends(get_db), token: str = Header(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token       = decode_jwt(token)
    role_from_token     = decoded_token.get("role")
    user_id_from_token  = decoded_token.get("id")

    # Verificar permisos de administrador
    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para generar pagos automáticos")

    debtor_id = reg_data.debtor_id

    # Obtener el último registro aprobado del deudor
    last_register = ( db.query(RegsInDb).filter(RegsInDb.debtor_id == debtor_id).order_by(RegsInDb.date.desc()).first())
    if not last_register or last_register.payment_status.lower() != "approved":
        raise HTTPException( status_code=404 if not last_register else 400, detail=( "No se encontraron registros aprobados para el deudor" if not last_register else "El último registro no está aprobado"),)

    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == last_register.mortgage_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="No se encontró la hipoteca asociada al último registro")

    # Calcular penalidades por mora
    penalty_amount      = 0
    penalty_days        = last_register.penalty_days or 0
    penalty_description = ""
    if penalty_days > 0:
        period_start    = reg_data.date.replace(day=1)
        period_end      = reg_data.date.replace(day=31)
        penalty_rate    = ( db.query(PenaltyInDB).filter(PenaltyInDB.start_date <= period_start, PenaltyInDB.end_date >= period_end).first())
        if not penalty_rate:
            raise HTTPException(400, "No hay un interés de mora fijado para el mes actual")
        penalty_amount = ((last_register.min_payment * penalty_rate.penalty_rate / 100) / 30) * penalty_days
        penalty_description = f"Intereses de mora ({penalty_rate.penalty_rate}%) por {penalty_days} días"

    # Ajustar saldo de capital por remanente
    remaining       = (last_register.paid or 0) - (last_register.min_payment or 0)
    small_remainder = 0
    if remaining > 0:
        if remaining > (0.05 * mortgage.current_balance):
            mortgage.current_balance -= remaining
            last_register.to_main_balance = remaining
        else:
            small_remainder = remaining
    db.commit()

    # Calcular componentes básicos
    interest_component = mortgage.current_balance * mortgage.interest_rate / 100
    # amount suma cargos: interés + penalidad
    total_charges = interest_component + penalty_amount
    # min_payment es lo que realmente debe pagar el usuario este mes
    new_min_payment = total_charges - small_remainder

    # Crear nuevo registro de cargo
    limit_due = reg_data.date.replace(day=5) + relativedelta(months=1)
    new_register = RegsInDb(
        mortgage_id     = last_register.mortgage_id,
        lender_id       = last_register.lender_id,
        debtor_id       = debtor_id,
        date            = reg_data.date,
        concept         = ( f"CARGO: Cobro generado por sistema ({penalty_description})" if penalty_amount > 0 else "CARGO: Cobro generado por sistema"),
        paid            = 0,
        amount          = total_charges,
        penalty         = penalty_amount,
        penalty_days    = penalty_days,
        min_payment     = new_min_payment,
        limit_date      = limit_due,
        to_main_balance = 0,
        payment_status  = "approved",
        comment         = "System",
        payment_type    = None,
    )

    # Actualizar fecha de última actualización de la hipoteca
    mortgage.last_update = reg_data.date

    # Registrar evento en logs y guardar
    log_entry = LogsInDb(
        action      = "System Payment Generated",
        timestamp   = local_timestamp_str,
        message     = f"Sistema generó un cobro para el deudor {debtor_id}",
        user_id     = user_id_from_token,
    )
    db.add(log_entry)
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

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    # Admin permission check
    if role_from_token != "admin":
        log_entry = LogsInDb(
            action="User Alert",
            timestamp=local_timestamp_str,
            message=f"Unauthorized access attempt to update register (Admin permission required)",
            user_id=decoded_token.get("id"),
        )
        db.add(log_entry)
        db.commit()
        raise HTTPException(status_code=403, detail="Admin permission required")

    # Query the database for the register
    reg = db.query(RegsInDb).filter(RegsInDb.id == reg_update.reg_id).first()

    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    # Update payment_status and add comments based on the new status
    reg.payment_status = reg_update.new_status

    if reg_update.new_status.lower() == "approved":
        reg.comment = "Pago confirmado"
        # Update MortgageInDB.last_update to the payment date if it hasn't been set
        mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == reg.mortgage_id).first()
        if mortgage and not mortgage.last_update:
            mortgage.last_update = reg.date

    elif reg_update.new_status.lower() == "rejected":
        reg.comment = "Pago rechazado por sistema"

    # Log the update operation
    log_entry = LogsInDb(
        action="Register Status Updated",
        timestamp=local_timestamp_str,
        message=f"Registro {reg_update.reg_id} actualizado a estado: {reg_update.new_status}",
        user_id=decoded_token.get("id"),
    )
    db.add(log_entry)
    db.commit()

    return {"message": f"Registro {reg_update.reg_id} actualizado exitosamente"}


    
@router.delete("/delete_reg/{reg_id}")
def delete_register(reg_id: int, db: Session = Depends(get_db), token: str = Header(None)):
    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    # Verificar permisos
    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")

    reg = db.query(RegsInDb).filter(RegsInDb.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    db.delete(reg)
    db.commit()
    return {"message": f"Registro {reg_id} eliminado exitosamente"}

@router.get("/debtor_names/")   #WARNING NO TOKEN!!
def get_names(db: Session = Depends(get_db)):
    users = db.query(UserInDB).filter(UserInDB.role == 'debtor').all()
    names = []
    for user in users:
        names.append({
            "id"        : user.id_number,
            "nombre"    : user.username,
        })
    return {'debts': names}


@router.get("/last_reg/{debtor_id}")
def get_last_reg(debtor_id: str, db: Session = Depends(get_db), token: str = Header(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    decoded_token = decode_jwt(token)
    role_from_token = decoded_token.get("role")

    if role_from_token != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")

    reg = (
        db.query(RegsInDb)
        .filter(RegsInDb.debtor_id == debtor_id)
        .order_by(RegsInDb.date.desc())
        .first()
    )

    if not reg:
        return {"message": f"No se encontraron registros para el deudor con ID {debtor_id}"}


    return reg_to_dict(reg)



@router.post("/payment_register/")
async def register_mortgage_payment_simple(
    reg_data        : str           = Form(...),
    db              : Session       = Depends(get_db),
    token           : str           = Header(None)
):
    # Decodificar y validar el token
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Convertir reg_data de JSON a diccionario
    reg_data_dict = json.loads(reg_data)

    # Buscar hipoteca
    mortgage_id = reg_data_dict.get('mortgage_id')
    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == mortgage_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="Mortgage not found")


    # Calcular mora y tipo de pago
    payment_date = datetime.strptime(reg_data_dict['payment_date'], '%Y-%m-%d').date()
    print(payment_date)
    limit_date = datetime.strptime(reg_data_dict['limit_date'], '%Y-%m-%d').date()
    print(limit_date)
    mora_days = max((payment_date - limit_date).days, 0)
    print(mora_days)
    ext = "extemporaneo" if mora_days > 0 else "normal"
    print(ext)

    mortgage.last_update = reg_data_dict['payment_date']
    
    # Crear registro
    new_register = RegsInDb(
        mortgage_id     = mortgage_id,
        lender_id       = mortgage.lender_id,
        debtor_id       = reg_data_dict['debtor_id'],
        date            = reg_data_dict['payment_date'],
        paid            = reg_data_dict['paid'],
        concept         = reg_data_dict['concept'],
        amount          = reg_data_dict['amount'],
        penalty         = reg_data_dict['penalty'],
        penalty_days    = reg_data_dict ['penalty_days'],
        min_payment     = reg_data_dict['min_payment'],
        limit_date      = limit_date,
        to_main_balance = reg_data_dict['to_main_balance'],
        comprobante     = "No aplica",
        payment_status  = "approved",
        comment         = reg_data_dict ['comment'],
        payment_type    = reg_data_dict ['payment_type'],
    )
    db.add(new_register)
    db.commit()
    
    # Mensaje de respuesta
    message = (
        f"Pago reportado como {'extemporáneo' if mora_days > 0 else 'normal'}. "
        f"Será revisado y formalizado en los próximos días. Tipo de pago: {new_register.payment_type}."
    )
    return {"message": message, "registro_id": new_register.id}
