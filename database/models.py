from sqlalchemy import Column, Date, Boolean, ForeignKey, Integer, String, DateTime, DECIMAL, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True)
    name = Column(String(50))

class Deceased(Base):
    __tablename__ = "deceaseds"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    national_id = Column(String(50), unique=True)
    date_of_death = Column(Date)

class Guardian(Base):
    __tablename__ = "guardians"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    national_id = Column(String(50), unique=True)
    phone = Column(String(20))
    relationship = Column(Integer)
    appointment_date = Column(Date)

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

class OrphanGuardian(Base):
    __tablename__ = "orphan_guardians"

    id = Column(Integer, primary_key=True)
    orphan_id = Column(Integer, ForeignKey("orphans.id"))
    guardian_id = Column(Integer, ForeignKey("guardians.id"))

    is_primary = Column(Boolean, default=False)
    start_date = Column(Date)
    end_date = Column(Date)

    orphan = relationship("Orphan", backref="guardian_links")
    guardian = relationship("Guardian", backref="orphan_links")

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