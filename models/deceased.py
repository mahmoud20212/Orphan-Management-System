from sqlalchemy import Column, Integer, String, Date
from database import Base

class Deceased(Base):
    __tablename__ = "deceaseds"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    national_id = Column(String(50), unique=True)
    date_of_death = Column(Date)
