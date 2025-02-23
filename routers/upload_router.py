from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import File 
from pathlib import Path
from models.filemodels import FileUpload



router = APIRouter()

@router.post("/upload")
async def upload_file(
    file            : UploadFile = FastAPIFile(...), 
    entity_type     : str = Form(...), 
    entity_id       : int = Form(...), 
    file_type       : str = Form(...),
    db              : Session = Depends(get_db)
):
    upload_folder = './uploads'
    Path(upload_folder).mkdir(parents=True, exist_ok=True)
    # Generate a unique filename to prevent conflicts
    unique_filename = f"{entity_id}_{file.filename}"
    file_location = f"{upload_folder}/{unique_filename}"

    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())
    
    save_file_to_db(db, entity_type, entity_id, file_type, file_location)
    
    return {"info": f"File '{file.filename}' uploaded successfully."} 

def save_file_to_db(db: Session, entity_type: str, entity_id: int, file_type: str, file_location: str):
    # Adjust this to match the actual constructor of your File model
    new_file = File(
        entity_type     = entity_type, 
        entity_id       = entity_id, 
        file_type       = file_type, 
        file_location   = file_location)
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    return new_file

# @router.get("/list-uploads")
# async def list_uploads():
#     upload_folder = Path('./uploads')
#     file_urls = [f"/uploads/{file.name}" for file in upload_folder.iterdir() if file.is_file()]
#     return {"files": file_urls}