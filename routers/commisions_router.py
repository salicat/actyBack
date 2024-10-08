from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import and_
from db.db_connection import get_db 
from models.help_models import HelpTicket
from db.all_db import HelpRequestInDb, UserInDB, ComisionsInDb
import boto3
from botocore.config import Config
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from botocore.exceptions import NoCredentialsError
import os
import jwt
from typing import List
import smtplib
from smtplib import SMTP

# Configuración JWT y zona horaria
SECRET_KEY = "8/8"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

utc_now             = datetime.now(timezone.utc)
utc_offset          = timedelta(hours=-5)
local_now           = utc_now + utc_offset
local_timestamp_str = local_now.strftime('%Y-%m-%d %H:%M:%S.%f')

# Función para decodificar el JWT
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

# Crear el enrutador para el API
router = APIRouter()

@router.get("/commissions/")
def get_commissions(db: Session = Depends(get_db), token: str = Header(None)):
    # Verificar si el token fue proporcionado
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decodificar el token
    decoded_token   = decode_jwt(token)  # Asegúrate de que la función decode_jwt funcione correctamente
    id_number       = decoded_token.get("id")
    role            = decoded_token.get("role")

    if not id_number or not role:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    # Si el rol es admin o agent, obtener todas las comisiones
    if role in ["admin", "agent"]:
        commissions = db.query(ComisionsInDb).filter(ComisionsInDb.status == "Vigente").all()  # Solo comisiones vigentes
    else:
        # No estamos manejando aún usuarios normales, por lo que devolvemos un error
        raise HTTPException(status_code=403, detail="Access denied")

    # Verificar si hay comisiones disponibles
    if not commissions:
        return {"message": "No commissions found"}

    # Preparar la respuesta
    response = []
    for commission in commissions:
        response.append({
            "id"        : commission.id,
            "concept"   : commission.concept,
            "value"     : commission.value,
            "date"      : commission.date,
            "status"    : commission.status
        })

    return {"vigentes": response}
