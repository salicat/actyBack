from pydantic import BaseModel
from typing import Optional

class FileUpload(BaseModel):
    entity_type : str
    entity_id   : int
    file_type   : str
    
    class Config:
        from_attributes = True

