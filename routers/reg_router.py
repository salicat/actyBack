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



@router.post("/mortgage_payment/register/")
async def register_mortgage_payment(
    reg_data: str = Form(...),
    payment_receipt: UploadFile = FastAPIFile(None),
    db: Session = Depends(get_db),
    token: str = Header(None),
):
    # ——— DEBUGGING PRINTS ———
    print("=== register_mortgage_payment entry ===")
    print("Raw reg_data:", reg_data)
    print("Payment receipt provided?:", bool(payment_receipt))

    # ——— TOKEN & AUTH ———
    if not token:
        print("No token")
        raise HTTPException(401, "Token not provided")
    try:
        decoded = decode_jwt(token)
        print("Decoded JWT:", decoded)
    except Exception as ex:
        print("JWT decode error:", ex)
        raise HTTPException(401, "Invalid token")
    user_id = decoded.get("id")

    # ——— PARSE reg_data JSON ———
    try:
        data = json.loads(reg_data)
        print("Parsed reg_data dict:", data)
    except json.JSONDecodeError as ex:
        print("JSON decode error:", ex)
        raise HTTPException(400, "Formato JSON inválido en reg_data")

    # ——— EXTRACT FIELDS & VALIDATE ———
    mortgage_id    = data.get("mortgage_id")
    paid_amount    = data.get("paid")
    payment_date_s = data.get("payment_date")
    debtor_id_in   = data.get("debtor_id")
    min_payment_in = data.get("min_payment")
    limit_date_in  = data.get("limit_date")

    if mortgage_id is None or paid_amount is None or payment_date_s is None:
        print("Missing one of mortgage_id/paid/payment_date")
        raise HTTPException(400, "Faltan campos obligatorios en reg_data")

    print(f"Fields → mortgage_id: {mortgage_id}, paid: {paid_amount}, payment_date: {payment_date_s}")

    # ——— LOAD MORTGAGE ———
    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == mortgage_id).first()
    if not mortgage:
        print("Mortgage not found")
        raise HTTPException(404, "Hipoteca no encontrada")

    # ——— FIND LAST SYSTEM REGISTER ———
    last_sys = (
        db.query(RegsInDb)
          .filter(RegsInDb.mortgage_id==mortgage_id, RegsInDb.comment=="System")
          .order_by(RegsInDb.date.desc())
          .first()
    )

    # ——— DETERMINE debtor_id, min_payment, limit_date ———
    debtor_id = last_sys.debtor_id if last_sys else debtor_id_in
    min_payment = last_sys.min_payment if last_sys else min_payment_in
    limit_date_raw = last_sys.limit_date if last_sys else limit_date_in

    # parse limit_date to date
    if isinstance(limit_date_raw, str):
        limit_date = datetime.strptime(limit_date_raw, "%Y-%m-%d").date()
    else:
        limit_date = limit_date_raw

    # ——— DUPLICATE CHECK ———
    payment_date = datetime.strptime(payment_date_s, "%Y-%m-%d").date()
    dup = (
        db.query(RegsInDb)
          .filter(
              RegsInDb.mortgage_id==mortgage_id,
              RegsInDb.debtor_id==debtor_id,
              RegsInDb.date==payment_date,
              RegsInDb.paid==paid_amount,
          )
          .first()
    )
    if dup:
        print("Duplicate payment detected")
        raise HTTPException(400, "Pago duplicado")

    # ——— HANDLE UPLOAD ———
    receipt_path = None
    payment_type = "PSE"
    if payment_receipt:
        upload_folder = "./uploads"
        os.makedirs(upload_folder, exist_ok=True)
        fn = f"{mortgage_id}_receipt_{payment_receipt.filename}"
        receipt_path = f"{upload_folder}/{fn}"
        with open(receipt_path, "wb") as buf:
            shutil.copyfileobj(payment_receipt.file, buf)
        save_file_to_db(db, "mortgage_payment", mortgage_id, "payment_receipt", receipt_path)
        payment_type = "consignación bancaria"
        print("Saved receipt to", receipt_path)

    # ——— CALCULATE MORA ———
    mora_days = (payment_date - limit_date).days if payment_date > limit_date else 0
    ext = "extemporáneo" if mora_days > 0 else "normal"
    print(f"mora_days={mora_days}, type={ext}")

    # ——— CREATE REGISTER ———
    new_reg = RegsInDb(
        mortgage_id    = mortgage_id,
        lender_id      = mortgage.lender_id,
        debtor_id      = debtor_id,
        date           = payment_date,
        paid           = paid_amount,
        concept        = f"Pago {ext} reportado por usuario",
        penalty_days   = mora_days,
        min_payment    = min_payment,
        limit_date     = limit_date,
        comprobante    = receipt_path,
        payment_status = "pending",
        comment        = f"Pagado con {mora_days} días de mora" if mora_days>0 else "Pago en fecha",
        payment_type   = payment_type,
    )

    # ——— LOG & COMMIT ———
    log = LogsInDb(
        action    = "Payment Receipt Uploaded" if payment_receipt else "Payment Reported (PSE)",
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message   = f"Pago reportado para hipoteca ID: {mortgage_id}",
        user_id   = user_id
    )
    db.add(log)
    db.add(new_reg)
    db.commit()
    print("Committed log and new register, id:", new_reg.id)

    # ——— RESPONSE ———
    msg = f"Pago reportado con éxito ({payment_type})."
    if mora_days > 0:
        msg += f" Días en mora: {mora_days}"
    return {"message": msg}


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
        regs.append({                                       #who use this data?
            "date"              : record.date,              #both
            "concept"           : record.concept,           #both
            "paid"              : record.paid,              #both
            "amount"            : record.amount,            #both
            "penalty_days"      : record.penalty_days,      #both
            "penalty"           : record.penalty,           #both
            "min_payment"       : record.min_payment,       #both
            "limit_date"        : record.limit_date,        #both
            "to_main_balance"   : record.to_main_balance,   #admin
            "comprobante"       : record.comprobante,       #admin
            "status"            : record.payment_status,    #admin
            "payment_type"      : record.payment_type,      #admin
            "comments"          : record.comment,           #admin
            "id"                : record.id                 #admin
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
    reg_data    : SystemReg,
    db          : Session   = Depends(get_db),
    token       : str       = Header(None)
):
    # --- Validación de token y permisos (sin cambios) ---
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")
    decoded = decode_jwt(token)
    if decoded.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso")
    user_id = decoded.get("id")

    debtor_id = reg_data.debtor_id

    # Obtener último corte de sistema
    last_system = (db.query(RegsInDb).filter(RegsInDb.debtor_id==debtor_id, RegsInDb.comment=="System").order_by(RegsInDb.date.desc()).first())

    # Obtener último registro aprobado
    last_register = (db.query(RegsInDb).filter(RegsInDb.debtor_id==debtor_id).order_by(RegsInDb.date.desc()).first())
    if not last_register or last_register.payment_status.lower() != "approved":
        raise HTTPException(
            status_code = 404 if not last_register else 400,
            detail      = "No hay registros aprobados" if not last_register else "Último registro no aprobado"
        )

    # Fecha de inicio de cómputo de mora
    start_date = last_system.date if last_system else last_register.limit_date

    # Obtener hipoteca asociada
    mortgage = db.query(MortgageInDB).filter(MortgageInDB.id == last_register.mortgage_id).first()
    if not mortgage:
        raise HTTPException(status_code=404, detail="Hipoteca no encontrada")

    # ——— CÁLCULO DE MORA Y REMANENTES ———

    # 1) definir rango del mes
    period_start = reg_data.date.replace(day=1)
    period_end   = (period_start + relativedelta(months=1)) - relativedelta(days=1)

    # 2) traer todos los pagos approved de ese mes
    payments = (db.query(RegsInDb)
          .filter(
              RegsInDb.debtor_id==debtor_id,
              RegsInDb.payment_status=="approved",
              RegsInDb.date >= period_start,
              RegsInDb.date <= period_end
          )
          .order_by(RegsInDb.date.asc())
          .all()
    )  # lista de pagos en el mes :contentReference[oaicite:0]{index=0}

    total_penalty       = 0
    total_remnant       = 0
    penalty_description = ""

    # 3) si hay pagos, calcular mora tramo a tramo
    if payments:
        for p in payments:
            print(p.date)
            print(p.limit_date)
            days = (p.date - p.limit_date).days  # días reales :contentReference[oaicite:1]{index=1}
            print(days)
            if days < 0:
               days = 0
            if days > 0:
                pr = (
                    db.query(PenaltyInDB)
                      .filter(PenaltyInDB.start_date <= period_start,
                              PenaltyInDB.end_date   >= period_end)
                      .first()
                )
                if not pr:
                    raise HTTPException(400, "No hay interés de mora para el mes")
                # prorrateo sobre 30 días :contentReference[oaicite:2]{index=2}
                amt = ((last_register.min_payment * pr.penalty_rate/100)/30) * days
                total_penalty += amt
                penalty_description += f"+ mora{pr.penalty_rate}%×{days}d "
            # ajustar remanente de este pago
            rem = (p.paid or 0) - last_register.min_payment
            if rem > 0:
                if rem > 0.05 * mortgage.current_balance:
                    mortgage.current_balance -= rem
                    p.to_main_balance = rem
                else:
                    total_remnant += rem

    # 4) si NO hubo pagos en el mes, aplicar 30 días completos y sumar pendiente
    else:
        # saldo mínimo pendiente del mes anterior
        pending = last_register.min_payment
        total_penalty += pending
        penalty_description += f"+ pendiente ant. {pending} "
        # 30 días de mora sobre ese pendiente :contentReference[oaicite:3]{index=3}
        pr = (
            db.query(PenaltyInDB)
              .filter(PenaltyInDB.start_date <= period_start,
                      PenaltyInDB.end_date   >= period_end)
              .first()
        )
        if not pr:
            raise HTTPException(400, "No hay interés de mora para el mes")
        amt = ((pending * pr.penalty_rate/100)/30) * 30
        total_penalty += amt
        penalty_description += f"+ mora{pr.penalty_rate}%×30d "

    db.commit()  # persiste ajustes de capital y to_main_balance

    # ——— CREACIÓN DE NUEVO REGISTRO DE COBRO ———

    base_payment = mortgage.monthly_payment
    total_amount = base_payment + total_penalty
    new_min_payment = total_amount - total_remnant
    limit_due = reg_data.date.replace(day=5) + relativedelta(months=1)

    new_register = RegsInDb(
        mortgage_id     = last_register.mortgage_id,
        lender_id       = last_register.lender_id,
        debtor_id       = debtor_id,
        date            = reg_data.date,
        concept         = f"Cobro sistema ({penalty_description.strip()})" if total_penalty>0 else "Cobro sistema",
        paid            = -total_remnant,
        amount          = total_amount,
        penalty         = total_penalty,
        penalty_days    = (reg_data.date - start_date).days,
        min_payment     = new_min_payment,
        limit_date      = limit_due,
        to_main_balance = 0,
        payment_status  = "approved",
        comment         = "System",
        payment_type    = None,
    )

    mortgage.last_update = reg_data.date

    log_entry = LogsInDb(
        action    = "System Payment Generated",
        timestamp = datetime.utcnow().isoformat(),
        message   = f"Cobro sistema para deudor {debtor_id}",
        user_id   = user_id,
    )
    db.add(log_entry)
    db.add(new_register)
    db.commit()

    return {"message": "Cobro generado exitosamente"}



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
