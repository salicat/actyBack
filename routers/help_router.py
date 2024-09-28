from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import and_
from db.db_connection import get_db 
from models.help_models import HelpTicket
from db.all_db import HelpRequestInDb, UserInDB
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

load_dotenv()

smtp_host = os.getenv('MAILERTOGO_SMTP_HOST')
smtp_user = os.getenv('MAILERTOGO_SMTP_USER')
smtp_password = os.getenv('MAILERTOGO_SMTP_PASSWORD')
server = SMTP(smtp_host, 587)  
server.starttls() 
server.login(smtp_user, smtp_password) 

router = APIRouter()

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
    
# Obtener todas las solicitudes de ayuda
@router.get("/help-requests/")
def get_help_requests(db: Session = Depends(get_db), token: str = Header(None)):
    # Verificar si el token fue proporcionado
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decodificar el token
    decoded_token = decode_jwt(token)
    id_number = decoded_token.get("id")
    role = decoded_token.get("role")

    if not id_number or not role:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    # Buscar el usuario en la base de datos usando el id_number
    user = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Si el usuario es "admin", devolver todos los tickets
    if role == "admin":
        tickets = db.query(HelpRequestInDb).all()
    else:
        # Si es un usuario normal, devolver solo los tickets creados por él (usuario = username)
        tickets = db.query(HelpRequestInDb).filter(HelpRequestInDb.usuario == user.username).all()

    # Preparar la respuesta
    if not tickets:
        return {"message": "No tickets found"}

    response = []
    for ticket in tickets:
        response.append({
            "id": ticket.id,
            "fecha": ticket.fecha.strftime("%Y-%m-%d"),
            "motivo": ticket.motivo,
            "mensaje": ticket.mensaje,
            "usuario": ticket.usuario,
            "status": ticket.status
        })

    return response


@router.post("/help-requests/")
def create_help_request(ticket: HelpTicket, db: Session = Depends(get_db), token: str = Header(None)):
    # Verificar si el token fue proporcionado
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decodificar el token
    decoded_token = decode_jwt(token)
    id_number = decoded_token.get("id")

    if id_number is None:
        raise HTTPException(status_code=403, detail="Token is missing or invalid")

    # Buscar el usuario en la base de datos usando el id_number
    user = db.query(UserInDB).filter(UserInDB.id_number == id_number).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Crear la nueva solicitud de ayuda
    nueva_solicitud = HelpRequestInDb(
        fecha       = local_timestamp_str,
        mensaje     = ticket.mensaje,
        motivo      = ticket.motivo,
        usuario     = user.username,  # Almacenar el nombre del usuario
        status      = "pendiente"
    )

    db.add(nueva_solicitud)
    db.commit()
    db.refresh(nueva_solicitud)

    # Enviar el correo de confirmación al usuario y a contacto@actyvalores.com
    try:
        sender_email = "no-reply@mail.app.actyvalores.com"
        receiver_email = user.email  # Usar el email del usuario desde la base de datos
        cc_email = "contacto@actyvalores.com"
        subject = "Ticket de Asistencia Recibido"

        # Cuerpo del correo en texto plano
        body = f"Hemos recibido tu ticket con el motivo: {ticket.motivo}. Nos pondremos en contacto pronto."

        # Cuerpo del correo en HTML
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
                <h1>Ticket de Asistencia Recibido</h1>
                <p>Hola {user.username},</p>
                <p>Hemos recibido tu ticket con el motivo: <strong>{ticket.motivo}</strong>. Nos pondremos en contacto pronto.</p>
                <p>Mensaje recibido: {ticket.mensaje}</p>
                <p>Gracias por elegirnos!</p>
            </div>
            <div class="footer">
                <p>Saludos,<br>Equipo de Desarrollo<br><a href="https://app.actyvalores.com">actyvalores.com</a></p>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Cc'] = cc_email
        part1 = MIMEText(body, 'plain')
        part2 = MIMEText(body_html, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Enviar el correo a los destinatarios
        recipients = [receiver_email, cc_email]
        server.sendmail(sender_email, recipients, msg.as_string())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al enviar el correo: {str(e)}")

    # Preparar la respuesta
    return {
        "Ticket creado con exito"
    }
    
    
# Actualizar el status de una solicitud de ayuda
@router.put("/help-requests/{request_id}")
def update_help_request_status(request_id: int, status: str, db: Session = Depends(get_db), token: str = Header(None)):
    # Verificar si el token fue proporcionado
    if not token:
        raise HTTPException(status_code=401, detail="Token not provided")

    # Decodificar el token y manejar el caso de un token inválido
    try:
        user = decode_jwt(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Verificar si el usuario tiene rol de admin
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to update this resource")

    # Buscar la solicitud de ayuda
    solicitud = db.query(HelpRequestInDb).filter(HelpRequestInDb.id == request_id).first()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Help request not found")

    # Actualizar el status
    solicitud.status = status
    db.commit()
    db.refresh(solicitud)

    # Preparar la respuesta
    return {
        "id": solicitud.id,
        "fecha": solicitud.fecha.strftime("%Y-%m-%d"),
        "mensaje": solicitud.mensaje,
        "motivo": solicitud.motivo,
        "usuario": solicitud.usuario,
        "status": solicitud.status,
    }