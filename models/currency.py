from sqlalchemy import Column, Integer, String
from database import Base

class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True)
    name = Column(String(50))
