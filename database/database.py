#from functools import partial
#from typing import Union
#import aurora_data_api
#import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
#from sqlalchemy.sql.expression import Delete, Insert, Update

POSTGRES_DATABASE_URL = "postgresql://postgres:Trust%40Magic11@localhost/postgres"

engine = create_engine(
    POSTGRES_DATABASE_URL, echo=True, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""
class FlouriaDatabase:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FlouriaDatabase, cls).__new__(cls)
        return cls._instance

Base = declarative_base()
"""
