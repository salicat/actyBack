from fastapi import HTTPException, APIRouter, Depends
from fastapi.responses import FileResponse
from fastapi.responses import Response
from sqlalchemy.orm import Session
from db.db_connection import get_db
from db.all_db import File
import os

router = APIRouter()

@router.get("/files/{file_id}")
async def get_file(file_id: int, db: Session = Depends(get_db)):
    file_record = db.query(File).filter(File.id == file_id).first()
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = file_record.file_location
    if os.path.isfile(file_path):
        return FileResponse(
            path=file_path,
            headers={
                "Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"
            },
        )
    else:
        raise HTTPException(status_code=404, detail="File not found on server")
    
@router.get("/images/{file_id}")
async def get_image(file_id: int, db: Session = Depends(get_db)):
    file_record = db.query(File).filter(File.id == file_id).first()
    if file_record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    
    file_path = file_record.file_location
    if os.path.isfile(file_path):
        return FileResponse(
            path=file_path,
            media_type='image/jpeg',  # You may need to dynamically set the correct media type
            headers={
                "Content-Disposition": "inline; filename={}".format(os.path.basename(file_path))
            },
        )
    else:
        raise HTTPException(status_code=404, detail="Image not found on server")
