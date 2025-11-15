from sqlalchemy import create_engine, Column, Integer,TIMESTAMP, Date, TEXT
from sqlalchemy.orm import declarative_base


import os
from dotenv import load_dotenv
load_dotenv()

# ---------- DATABASE SETUP ----------
PGDATABASE = os.environ.get("PGDATABASE")
PGPORT = os.environ.get("PGPORT")
PGUSER = os.environ.get("PGUSER")
PGHOST = os.environ.get("PGHOST")
PGPASSWORD = os.environ.get("PGPASSWORD")

DB = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{PGDATABASE}"
engine = create_engine(url=DB)
Base = declarative_base()

# ---------- DATABASE INIT ----------
def init_database() -> None:
    try:
        Base.metadata.create_all(engine)
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"Database init error: {e}")


# ORM MODEL

class ExpensiveTracker(Base):
    __tablename__="expensivetracker"
    id = Column(Integer,primary_key=True,autoincrement=True)
    date = Column(Date,nullable =False)
    education = Column(Integer,nullable=False)
    travel = Column(Integer,nullable=False)
    food = Column(Integer,nullable=False)
    fruit = Column(Integer,nullable = False)
    medicine = Column(Integer,nullable =False)
    friends = Column(Integer,nullable = False)
    description = Column(TEXT)
    created_at = Column(TIMESTAMP)