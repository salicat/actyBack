from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://krlz:1317@localhost/actyvalores_local"
# DATABASE_URL = "postgresql://krlz:UwdRtTTEc0OI66wJ0l3vbwLYzQabpD0O@dpg-cuth68tsvqrc73e775rg-a.oregon-postgres.render.com/cloud_db_0rt1"
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, 
                            autoflush=False, 
                            bind=engine)

def get_db():
    db = SessionLocal() 
    try:
        yield db
    finally:
        db.close()

Base = declarative_base()

conn = engine.connect()
if conn.dialect.has_schema(conn, "actyval_db"):
    Base.metadata.schema = "actyval_db"