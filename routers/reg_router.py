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
    # =================================================================
    # 1. INICIALIZACIÓN Y DEBUGGING
    # =================================================================
    print("\n=== INICIO REGISTRO DE PAGO ===")
    print("[DEBUG] Datos crudos recibidos:", reg_data[:100] + "...")  # Muestra preview

    # =================================================================
    # 2. AUTENTICACIÓN Y AUTORIZACIÓN
    # =================================================================
    if not token:
        print("[ERROR] No se recibió token")
        raise HTTPException(401, "Se requiere autenticación")

    try:
        decoded = decode_jwt(token)
        user_id = decoded.get("id")
        user_role = decoded.get("role")
        print(f"[DEBUG] Usuario autenticado | ID: {user_id} | Rol: {user_role}")
    except Exception as e:
        print(f"[ERROR] Fallo decodificación JWT: {str(e)}")
        raise HTTPException(401, "Token inválido")

    # =================================================================
    # 3. PARSEO Y VALIDACIÓN DE DATOS
    # =================================================================
    try:
        data = json.loads(reg_data)
        print("[DEBUG] Datos parseados:", json.dumps(data, indent=2))
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON inválido: {str(e)}")
        raise HTTPException(400, "Formato JSON incorrecto")

    # Campos obligatorios
    required_fields = ["mortgage_id", "paid", "payment_date"]
    missing = [field for field in required_fields if field not in data]
    if missing:
        print(f"[ERROR] Campos faltantes: {missing}")
        raise HTTPException(400, f"Campos obligatorios faltantes: {', '.join(missing)}")

    mortgage_id = data["mortgage_id"]
    paid_amount = float(data["paid"])  # Conversión explícita
    payment_date_str = data["payment_date"]
    
    print(f"[DEBUG] Datos clave recibidos:")
    print(f"• mortgage_id: {mortgage_id}")
    print(f"• paid_amount: {paid_amount}")
    print(f"• payment_date: {payment_date_str}")

    # =================================================================
    # 4. VALIDACIÓN DE HIPOTECA
    # =================================================================
    mortgage = db.query(MortgageInDB).get(mortgage_id)
    if not mortgage:
        print(f"[ERROR] Hipoteca no existe: {mortgage_id}")
        raise HTTPException(404, "Hipoteca no encontrada")
    
    print(f"[DEBUG] Hipoteca encontrada:")
    print(f"• Lender ID: {mortgage.lender_id}")
    print(f"• Deudor ID: {mortgage.debtor_id}")
    print(f"• Balance actual: {mortgage.current_balance}")

    # =================================================================
    # 5. OBTENER REGISTRO DE CORTE PREVIO (CRÍTICO)
    # =================================================================
    last_sys_reg = (
        db.query(RegsInDb)
        .filter(
            RegsInDb.mortgage_id == mortgage_id,
            RegsInDb.comment == "System"
        )
        .order_by(RegsInDb.date.desc())
        .first()
    )

    if not last_sys_reg:
        print("[ERROR] No hay registro de corte previo")
        raise HTTPException(400, "No se encontró corte de sistema previo")
    
    print("[DEBUG] Último registro de sistema:")
    print(f"• Fecha corte: {last_sys_reg.date}")
    print(f"• Pago mínimo: {last_sys_reg.min_payment}")
    print(f"• Fecha límite: {last_sys_reg.limit_date}")

    # =================================================================
    # 6. VALIDACIÓN DE FECHAS (CORRECCIÓN CRÍTICA)
    # =================================================================
    try:
        payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
        limit_date = last_sys_reg.limit_date
        
        print(f"[DEBUG] Fechas procesadas:")
        print(f"• Fecha pago: {payment_date}")
        print(f"• Fecha límite: {limit_date}")
        
        # Validación fecha futura
        if payment_date > datetime.now().date():
            print("[ERROR] Fecha de pago futura")
            raise HTTPException(400, "No se permiten fechas futuras")
            
    except ValueError as e:
        print(f"[ERROR] Formato de fecha inválido: {str(e)}")
        raise HTTPException(400, "Formato de fecha debe ser YYYY-MM-DD")

    # =================================================================
    # 7. DETECCIÓN DE DUPLICADOS (MEJORADO)
    # =================================================================
    duplicate = db.query(RegsInDb).filter(
        RegsInDb.mortgage_id == mortgage_id,
        RegsInDb.date == payment_date,
        RegsInDb.paid == paid_amount,
        RegsInDb.payment_status.in_(["pending", "approved"])
    ).first()

    if duplicate:
        print(f"[ERROR] Pago duplicado | ID existente: {duplicate.id}")
        raise HTTPException(400, "Pago ya registrado con estos datos")

    # =================================================================
    # 8. MANEJO DE COMPROBANTES (CORRECCIÓN SEGURIDAD)
    # =================================================================
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

    # =================================================================
    # 9. CÁLCULO DE MORA (CORRECCIÓN LÓGICA)
    # =================================================================
    mora_days = max((payment_date - limit_date).days, 0)  # Solo días positivos
    payment_status = "pending"
    
    print(f"[DEBUG] Cálculo de mora:")
    print(f"• Días calculados: {mora_days}")
    print(f"• Tipo pago: {'Extemporáneo' if mora_days > 0 else 'En fecha'}")

    # =================================================================
    # 10. CREACIÓN DE REGISTRO (MEJORA DE DATA INTEGRITY)
    # =================================================================
    try:
        new_reg = RegsInDb(
            mortgage_id     = mortgage_id,
            lender_id       = mortgage.lender_id,
            debtor_id       = mortgage.debtor_id,  # Siempre de la hipoteca
            date            = payment_date,
            paid            = paid_amount,
            min_payment     = last_sys_reg.min_payment,
            limit_date      = last_sys_reg.limit_date,  # Usar siempre del sistema
            penalty_days    = mora_days,
            comprobante     = receipt_path,
            payment_status  = payment_status,
            payment_type    = payment_type,
            concept         = f"Pago {'con mora' if mora_days > 0 else 'normal'} reportado",
            comment         = f"Registrado por usuario ID: {user_id}"
        )
        
        db.add(new_reg)
        db.flush()  # Forzar generación de ID
        print(f"[DEBUG] Nuevo registro creado | ID: {new_reg.id}")
        
    except Exception as e:
        print(f"[ERROR] Error creando registro: {str(e)}")
        db.rollback()
        raise HTTPException(500, "Error interno registrando pago")

    # =================================================================
    # 11. REGISTRO DE LOG (MEJORA TRAZABILIDAD)
    # =================================================================
    try:
        log_entry = LogsInDb(
            action="REGISTRO_PAGO",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=f"Nuevo pago ID: {new_reg.id} | Monto: {paid_amount} | Días mora: {mora_days}",
            user_id=user_id
        )
        db.add(log_entry)
        db.commit()
        print("[DEBUG] Transacción completada exitosamente")
        
    except Exception as e:
        print(f"[ERROR] Error en commit final: {str(e)}")
        db.rollback()
        raise HTTPException(500, "Error finalizando transacción")

    # =================================================================
    # 12. RESPUESTA FINAL
    # =================================================================
    response_msg = {
        "message": "Pago registrado exitosamente",
        "details": {
            "payment_id": new_reg.id,
            "amount": paid_amount,
            "due_days": mora_days,
            "receipt": bool(receipt_path)
        }
    }
    
    return {"message" : response_msg}


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
    reg_data: SystemReg,
    db: Session = Depends(get_db),
    token: str = Header(None)
):
    # ----------------------------------
    # 1. DECLARACIÓN DE VARIABLES CLAVE
    # ----------------------------------
    total_penalty = 0.0       # Acumulado de mora
    total_remnant = 0.0       # Excedentes no aplicados a capital
    total_days = 0            # Días totales de mora
    penalty_description = ""  # Detalle de mora
    pending_payment = 0.0     # Saldo pendiente del último registro
    
    print(f"\n[DEBUG] Iniciando cierre para deudor {reg_data.debtor_id} - Mes: {reg_data.date.strftime('%Y-%m')}")

    # ----------------------------------
    # 2. VALIDACIONES Y CONFIGURACIÓN
    # ----------------------------------
    # 2.1 Validación de token y permisos
    if not token:
        raise HTTPException(401, "Token requerido")
    
    decoded = decode_jwt(token)
    if decoded.get("role") != "admin":
        raise HTTPException(403, "Acceso denegado")
    
    user_id = decoded.get("id")
    debtor_id = reg_data.debtor_id

    # 2.2 Restricción mensual
    month_start = reg_data.date.replace(day=1)
    month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
    
    existing_run = db.query(RegsInDb).filter(
        RegsInDb.debtor_id == debtor_id,
        RegsInDb.comment == "System",
        RegsInDb.date.between(month_start, month_end)
    ).first()
    
    if existing_run:
        raise HTTPException(400, f"Cierre ya realizado para {month_start.strftime('%Y-%m')}")

    # 2.3 Obtener último registro aprobado
    last_register = db.query(RegsInDb).filter(
        RegsInDb.debtor_id == debtor_id
    ).order_by(RegsInDb.date.desc()).first()
    
    if not last_register or last_register.payment_status.lower() != "approved":
        error_msg = "No hay registros aprobados" if not last_register else "Último registro no aprobado"
        raise HTTPException(400, error_msg)

    pending_payment = last_register.paid
    print(f"[DEBUG] Último pago mínimo: {pending_payment}")

    # ----------------------------------
    # 3. CONFIGURACIÓN INICIAL
    # ----------------------------------
    mortgage = db.query(MortgageInDB).get(last_register.mortgage_id)
    if not mortgage:
        raise HTTPException(404, "Hipoteca no encontrada")
    
    print(f"[DEBUG] Hipoteca actual: Balance={mortgage.current_balance} - Cuota={mortgage.monthly_payment}")

    # 3.1 Obtener TODOS los pagos del mes
    payments = db.query(RegsInDb).filter(
        RegsInDb.debtor_id == debtor_id,
        RegsInDb.payment_status == "approved",
        RegsInDb.date.between(month_start, month_end)
    ).order_by(RegsInDb.date.asc()).all()
    
    print(f"[DEBUG] Pagos encontrados en el mes: {len(payments)}")

    # ----------------------------------
    # 4. PROCESAR CADA PAGO INDIVIDUALMENTE
    # ----------------------------------
    if payments:
        penalty_rate = db.query(PenaltyInDB).filter(
            PenaltyInDB.start_date <= month_start,
            PenaltyInDB.end_date >= month_end).first()
        
        if not penalty_rate:
            raise HTTPException(400, "Tasa de mora no configurada")

        print(f"[DEBUG] Tasa de mora: {penalty_rate.penalty_rate}%")

        for pago in payments:
            print(f"\n[DEBUG] Procesando pago ID: {pago.id}")
            print(f"• Fecha pago: {pago.date} | Fecha límite: {pago.limit_date}")
            print(f"• Pagado: {pago.paid} | Pago mínimo requerido: {pago.min_payment}")

            # 4.1 Calcular días de mora para ESTE pago
            dias_mora = max((pago.date - pago.limit_date).days, 0)
            total_days += dias_mora
            print(f"• Días mora: {dias_mora}")

            # 4.2 Calcular mora si hay atraso
            if dias_mora > 0:
                mora = (pago.min_payment * penalty_rate.penalty_rate / 100) / 30 * dias_mora
                total_penalty += mora
                penalty_description += f"+ {dias_mora}d×{penalty_rate.penalty_rate}% "
                print(f"• Mora calculada: {mora} | Total acumulado: {total_penalty}")

            # 4.3 Calcular excedente (lo pagado - mínimo requerido)
            excedente = pago.paid - pago.min_payment
            if excedente > 0:
                print(f"• Excedente detectado: {excedente}")
                
                # 4.4 Aplicar a capital si supera 5%
                if excedente > (mortgage.current_balance * 0.05):
                    print(f"• Aplicando {excedente} a capital (5%={mortgage.current_balance*0.05})")
                    
                    # Crear registro de abono
                    capital_reg = RegsInDb(
                        mortgage_id=mortgage.id,
                        debtor_id=debtor_id,
                        date=reg_data.date,
                        paid=excedente,
                        concept="Abono a capital",
                        to_main_balance=excedente,
                        payment_status="approved",
                        comment="System"
                    )
                    db.add(capital_reg)
                    mortgage.current_balance -= excedente
                else:
                    total_remnant += excedente
                    print(f"• Excedente acumulado para descuento: {total_remnant}")

        db.commit()  # Persistir abonos a capital

    else:
        print("[DEBUG] No hay pagos en el mes - Aplicando mora completa")
        penalty_rate = db.query(PenaltyInDB).filter(
            PenaltyInDB.start_date <= month_start,
            PenaltyInDB.end_date >= month_end).first()
        
        if penalty_rate:
            total_penalty = pending_payment * (penalty_rate.penalty_rate / 100)
            total_days = 30  # Asumir mes completo sin pagos
            penalty_description = f"Mora completa {penalty_rate.penalty_rate}%"

    # ----------------------------------
    # 5. CALCULAR NUEVOS VALORES
    # ----------------------------------
    # 5.1 Nueva cuota basada en balance actual
    new_monthly_payment = mortgage.current_balance * (mortgage.interest_rate / 100)
    mortgage.monthly_payment = new_monthly_payment
    
    # 5.2 Total a cobrar = Cuota + Mora - Excedentes aplicables
    total_amount = new_monthly_payment + total_penalty
    new_min_payment = total_amount - total_remnant
    
    print(f"\n[DEBUG] Resumen final:")
    print(f"• Nueva cuota: {new_monthly_payment}")
    print(f"• Total mora: {total_penalty}")
    print(f"• Excedentes aplicables: {total_remnant}")
    print(f"• Pago mínimo resultante: {new_min_payment}")

    # ----------------------------------
    # 6. GENERAR REGISTRO DE COBRO
    # ----------------------------------
    limit_due = reg_data.date.replace(day=5) + relativedelta(months=1)
    
    new_register = RegsInDb(
        mortgage_id=mortgage.id,
        debtor_id=debtor_id,
        date=reg_data.date,
        concept=f"Cobro sistema {penalty_description.strip()}" if total_penalty else "Cobro sistema",
        amount=total_amount,
        penalty=total_penalty,
        penalty_days=total_days,
        # KEY: Usar paid para llevar excedentes al siguiente mes
        paid=-total_remnant,  
        min_payment=new_min_payment,
        limit_date=limit_due,
        payment_status="approved",
        comment="System"
    )
    
    # ----------------------------------
    # 7. ACTUALIZACIONES FINALES
    # ----------------------------------
    mortgage.last_update = reg_data.date

    log = LogsInDb(
        action="Cierre de sistema",
        message=f"Generado para {debtor_id} - Pago mínimo: {new_min_payment}",
        user_id=user_id,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    
    db.add(log)
    db.add(new_register)
    db.commit()

    print("[DEBUG] Registro generado exitosamente")
    return {"message": "Cobro generado", "detalle": f"Nuevo pago mínimo: {new_min_payment}"}


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
