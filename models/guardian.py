from sqlalchemy import Column, Integer, String, Date
from database import Base

class Guardian(Base):
    __tablename__ = "guardians"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    national_id = Column(String(50), unique=True)
    phone = Column(String(20))
    relationship = Column(Integer)
    appointment_date = Column(Date)
