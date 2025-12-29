from sqlalchemy import Column, Integer, ForeignKey, DECIMAL, DateTime, String
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    orphan_id = Column(Integer, ForeignKey("orphans.id"))
    currency_id = Column(Integer, ForeignKey("currencies.id"))

    amount = Column(DECIMAL(15,2), nullable=False)
    transaction_type = Column(Integer)  # 1=إيداع 2=سحب
    transaction_date = Column(DateTime, default=datetime.utcnow)
    note = Column(String(255))

    orphan = relationship("Orphan")
    currency = relationship("Currency")
