from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Orphan(Base):
    __tablename__ = "orphans"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    national_id = Column(String(50), unique=True)
    date_of_birth = Column(Date)
    gender = Column(Integer)

    deceased_id = Column(Integer, ForeignKey("deceaseds.id"))
    deceased = relationship("Deceased", backref="orphans")

    created_at = Column(DateTime, default=datetime.utcnow)
