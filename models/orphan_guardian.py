from sqlalchemy import Column, Integer, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

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
