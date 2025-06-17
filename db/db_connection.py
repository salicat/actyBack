from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

#DATABASE_URL = "postgresql://krlz:1317@localhost/actyvalores_local"
DATABASE_URL = "postgres://ufrocq8c5aqej2:p8402a101a838f6ce0a2a46daed74d2ded574a77b713571e7b1799ba272b2c249@c5cnr847jq0fj3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d64qcbdst0uoq2"
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