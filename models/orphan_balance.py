from sqlalchemy import Column, Integer, ForeignKey, DECIMAL, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class OrphanBalance(Base):
    __tablename__ = "orphan_balances"
    __table_args__ = (
        UniqueConstraint("orphan_id", "currency_id"),
    )

    id = Column(Integer, primary_key=True)
    orphan_id = Column(Integer, ForeignKey("orphans.id"))
    currency_id = Column(Integer, ForeignKey("currencies.id"))

    balance = Column(DECIMAL(15,2), default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)

    orphan = relationship("Orphan")
    currency = relationship("Currency")
