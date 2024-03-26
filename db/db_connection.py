from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


DATABASE_URL = "postgresql://udc2so76e3ro74:p3000bbcc372fced8b5567649d05e6bf749df779bf7a79ff942dd0f1ad639c9a7@cb4l59cdg4fg1k.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dem0gsbrobr5t8"
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