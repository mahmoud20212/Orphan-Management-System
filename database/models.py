from sqlalchemy import (
    Column, Date, Boolean, ForeignKey, Integer, String,
    DateTime, Numeric, UniqueConstraint, Enum, Index
)
from sqlalchemy.orm import relationship
from datetime import date, datetime, timezone
import enum

from .db import Base

class GenderEnum(enum.Enum):
    male = 1
    female = 2


class TransactionTypeEnum(enum.Enum):
    deposit = 1
    withdraw = 2

class PermissionEnum(enum.Enum):
    view = "view"
    create = "create"
    update = "update"
    delete = "delete"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    role_id = Column(Integer, ForeignKey("roles.id"))
    role = relationship("Role", back_populates="users")
    
    def __repr__(self):
        return f"<User username={self.username}>"

class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)

    balances = relationship("OrphanBalance", back_populates="currency")
    transactions = relationship("Transaction", back_populates="currency")

    def __repr__(self):
        return f"<Currency code={self.code}>"

class Deceased(Base):
    __tablename__ = "deceased_people"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    national_id = Column(String(9), index=True, nullable=True)
    date_death = Column(Date, nullable=True)
    account_number = Column(String(50), nullable=True)
    archives_number = Column(String(50), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    orphans = relationship(
        "Orphan",
        back_populates="deceased",
        cascade="all, delete"
    )
    
    balances = relationship(
        "DeceasedBalance", 
        back_populates="deceased", 
        cascade="all, delete-orphan" # هذا السطر هو الحل
    )

    def __repr__(self):
        return f"<Deceased id={self.id} name={self.name}>"

class DeceasedBalance(Base):
    __tablename__ = "deceased_balances"
    __table_args__ = (
        UniqueConstraint("deceased_id", "currency_id"),
    )

    id = Column(Integer, primary_key=True)
    deceased_id = Column(Integer, ForeignKey("deceased_people.id", ondelete="CASCADE"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id", ondelete="CASCADE"), nullable=False)
    balance = Column(Numeric(15, 2), default=0)
    
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    deceased = relationship("Deceased", back_populates="balances")
    currency = relationship("Currency")

class DeceasedTransaction(Base):
    __tablename__ = "deceased_transactions"

    id = Column(Integer, primary_key=True)
    deceased_id = Column(Integer, ForeignKey("deceased_people.id", ondelete="CASCADE"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    
    amount = Column(Numeric(15, 2), nullable=False)
    # نوع العملية: إيداع (deposit) أو سحب للتوزيع (withdraw)
    type = Column(Enum(TransactionTypeEnum), nullable=False) 
    
    # --- بيانات سند القبض (أساسية لكل العمليات) ---
    receipt_number = Column(String(50), nullable=True, index=True) # رقم سند القبض الورقي
    payer_name = Column(String(255), nullable=True)                # اسم الشخص المودع
    payment_method = Column(String(50), nullable=True)             # (نقداً، شيك، تحويل)
    
    # --- بيانات تفصيلية للشيك (تُستخدم إذا كان النوع شيك) ---
    check_number = Column(String(100), nullable=True)             # رقم الشيك
    due_date = Column(Date, nullable=True)                        # تاريخ استحقاق الشيك
    bank_name = Column(String(255), nullable=True)                # اسم البنك (سواء للشيك أو التحويل)
    
    # --- بيانات التحويل البنكي ---
    reference_number = Column(String(255), nullable=True)         # رقم المرجع أو الحوالة
    is_auto_manual_distribution = Column(Boolean, default=False, nullable=False, index=True)
    row_group_key = Column(String(255), nullable=True, index=True)

    note = Column(String(255), nullable=True)
    created_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # العلاقات
    deceased = relationship("Deceased")
    currency = relationship("Currency")

class Guardian(Base):
    __tablename__ = "guardians"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    national_id = Column(String(9), index=True, nullable=True)
    phone = Column(String(10), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    orphan_links = relationship(
        "OrphanGuardian",
        back_populates="guardian",
        cascade="all, delete"
    )
    
    transactions = relationship(
        "GuardianTransaction", 
        back_populates="guardian",
        cascade="all, delete-orphan"
    )
    
    balances = relationship(
        "GuardianBalance", 
        back_populates="guardian", 
        # cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Guardian id={self.id} name={self.name}>"

class GuardianTransaction(Base):
    __tablename__ = "guardian_transactions"
    
    id = Column(Integer, primary_key=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    # أضفنا ondelete هنا للاتساق
    guardian_id = Column(Integer, ForeignKey("guardians.id", ondelete="CASCADE"), nullable=False)
    deceased_id = Column(Integer, ForeignKey("deceased_people.id", ondelete="SET NULL"), nullable=True, index=True)
    deceased_transaction_id = Column(Integer, ForeignKey("deceased_transactions.id", ondelete="CASCADE"), nullable=True, index=True)
    # orphan_id = Column(Integer, ForeignKey("orphans.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    type = Column(Enum(TransactionTypeEnum), nullable=False)
    note = Column(String(255), nullable=True)
    row_group_key = Column(String(255), nullable=True, index=True)
    created_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    
    document_number = Column(String(50), nullable=True, index=True)
    person_name = Column(String(255), nullable=True)
    payment_method = Column(String(50), nullable=True)
    check_number = Column(String(100), nullable=True)
    due_date = Column(Date, nullable=True)
    bank_name = Column(String(255), nullable=True)
    reference_number = Column(String(255), nullable=True)

    guardian = relationship("Guardian", back_populates="transactions") # إضافة back_populates اختيارية لكن مفيدة
    currency = relationship("Currency")
    deceased = relationship("Deceased")
    # orphan = relationship("Orphan")
    deceased_transaction = relationship("DeceasedTransaction")

class GuardianBalance(Base):
    __tablename__ = "guardian_balances"
    __table_args__ = (
        UniqueConstraint("guardian_id", "currency_id", name="uq_guardian_currency_balance"),
    )

    id = Column(Integer, primary_key=True)
    guardian_id = Column(Integer, ForeignKey("guardians.id", ondelete="CASCADE"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id", ondelete="CASCADE"), nullable=False)
    # التأكد من أن الرصيد لا يكون سالباً إلا إذا كان النظام يسمح بذلك
    balance = Column(Numeric(15, 2), default=0)
    
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    guardian = relationship("Guardian", back_populates="balances")
    currency = relationship("Currency")

class Orphan(Base):
    __tablename__ = "orphans"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    national_id = Column(String(9), index=True, nullable=True)
    date_birth = Column(Date, nullable=True)
    gender = Column(Enum(GenderEnum), nullable=False)
    phone = Column(String(10), nullable=True)

    deceased_id = Column(
        Integer,
        ForeignKey("deceased_people.id", ondelete="CASCADE"),
        nullable=True
    )

    deceased = relationship("Deceased", back_populates="orphans")

    guardian_links = relationship(
        "OrphanGuardian",
        back_populates="orphan",
        cascade="all, delete"
    )

    balances = relationship(
        "OrphanBalance",
        back_populates="orphan",
        cascade="all, delete"
    )

    transactions = relationship(
        "Transaction",
        back_populates="orphan",
        cascade="all, delete"
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Orphan id={self.id} name={self.name}>"
    
    @property
    def age(self):
        """Calculate age from date_birth. Returns None if date_birth is not set."""
        if self.date_birth is None:
            return '---'
        today = date.today()
        age = today.year - self.date_birth.year - ((today.month, today.day) < (self.date_birth.month, self.date_birth.day))
        return age

class OrphanGuardian(Base):
    __tablename__ = "orphan_guardians"
    __table_args__ = (
        UniqueConstraint("orphan_id", "guardian_id"),
    )

    id = Column(Integer, primary_key=True)

    orphan_id = Column(
        Integer,
        ForeignKey("orphans.id", ondelete="CASCADE"),
        nullable=False
    )

    guardian_id = Column(
        Integer,
        ForeignKey("guardians.id", ondelete="CASCADE"),
        nullable=False
    )

    relation = Column(String(20), nullable=False)
    is_primary = Column(Boolean, default=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    orphan = relationship("Orphan", back_populates="guardian_links")
    guardian = relationship("Guardian", back_populates="orphan_links")

    def __repr__(self):
        return f"<OrphanGuardian orphan_id={self.orphan_id} guardian_id={self.guardian_id}>"

class OrphanBalance(Base):
    __tablename__ = "orphan_balances"
    __table_args__ = (
        UniqueConstraint("orphan_id", "currency_id"),
    )

    id = Column(Integer, primary_key=True)

    orphan_id = Column(
        Integer,
        ForeignKey("orphans.id", ondelete="CASCADE"),
        nullable=False
    )

    currency_id = Column(
        Integer,
        ForeignKey("currencies.id", ondelete="CASCADE"),
        nullable=False
    )

    balance = Column(Numeric(15, 2), default=0)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    orphan = relationship("Orphan", back_populates="balances")
    currency = relationship("Currency", back_populates="balances")

    def __repr__(self):
        return f"<OrphanBalance orphan_id={self.orphan_id} balance={self.balance}>"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)

    orphan_id = Column(
        Integer,
        ForeignKey("orphans.id", ondelete="CASCADE"),
        nullable=False
    )

    currency_id = Column(
        Integer,
        ForeignKey("currencies.id", ondelete="CASCADE"),
        nullable=False
    )

    amount = Column(Numeric(15, 2), nullable=False)
    type = Column(Enum(TransactionTypeEnum), nullable=False)
    
    deceased_transaction_id = Column(Integer, ForeignKey("deceased_transactions.id"), nullable=True)
    created_date = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    note = Column(String(255), nullable=True)
    
    row_group_key = Column(String(255), nullable=True, index=True)
    document_number = Column(String(50), nullable=True, index=True)
    person_name = Column(String(255), nullable=True)
    payment_method = Column(String(50), nullable=True)
    check_number = Column(String(100), nullable=True)
    due_date = Column(Date, nullable=True)
    bank_name = Column(String(255), nullable=True)
    reference_number = Column(String(255), nullable=True)

    orphan = relationship("Orphan", back_populates="transactions")
    currency = relationship("Currency", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction id={self.id} amount={self.amount}>"

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100))
    resource_type = Column(String(50))
    resource_id = Column(Integer)
    description = Column(String(500))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    permissions = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete"
    )

    users = relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True)
    resource = Column(String(50), nullable=False)  
    action = Column(Enum(PermissionEnum), nullable=False)

    roles = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete"
    )

    __table_args__ = (
        UniqueConstraint("resource", "action"),
    )

    def __repr__(self):
        return f"<Permission {self.resource}:{self.action}>"

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"))

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")