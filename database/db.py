from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base
import os
import logging
import bcrypt
import sys
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# إعدادات قواعد البيانات
MYSQL_DATABASE_URL = "mysql+pymysql://root:root@localhost/mydb?charset=utf8mb4"
SQLITE_DATABASE_URL = "sqlite:///./orphan_system.db"

Base = declarative_base()

# ملاحظة: لا نستورد `models` هنا على مستوى الوحدة لتجنب دوائر الاستيراد.
# استيراد النماذج يجب أن يتم من قبل استدعاء الدالة `initialize_database`
# أو من قبل السكربتات التي ترغب بتسجيل النماذج قبل إنشاء الجداول.

def test_mysql_connection():
    """
    اختبار الاتصال بقاعدة بيانات MySQL.
    تُرجع True إذا كان الاتصال ناجحاً، False بخلاف ذلك.
    """
    try:
        test_engine = create_engine(MYSQL_DATABASE_URL, echo=False, pool_pre_ping=True)
        with test_engine.connect() as conn:
            logger.info("✓ تم الاتصال بنجاح بقاعدة بيانات MySQL")
            return True
    except Exception as e:
        logger.warning(f"✗ فشل الاتصال بـ MySQL: {str(e)}")
        return False

def hash_password(password: str) -> str:
    """تشفير كلمة المرور باستخدام bcrypt"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def get_application_icon():
    """
    الحصول على أيقونة التطبيق.
    تبحث عن ملف icon في مجلد assets/icons أو assets.
    """
    try:
        project_root = Path(__file__).parent.parent
        
        # محاولة الحصول على أيقونة من الملفات الموجودة
        icon_candidates = [
            project_root / "assets" / "app_icon.png",
            # project_root / "assets" / "app_icon.ico",
            # project_root / "assets" / "icons" / "ic_fluent_home_24_filled.svg",
        ]
        
        for icon_path in icon_candidates:
            if icon_path.exists():
                logger.debug(f"تم العثور على أيقونة التطبيق: {icon_path.name}")
                # تأخير الاستيراد حتى يكون QApplication موجود
                from PyQt6.QtGui import QIcon
                return QIcon(str(icon_path))
        
        logger.debug("لم يتم العثور على ملف أيقونة محدد")
        return None
    
    except Exception as e:
        logger.warning(f"خطأ في الحصول على أيقونة التطبيق: {str(e)}")
        return None

def setup_default_permissions_and_roles(session):
    """إعداد الصلاحيات الافتراضية ودور الأدمن والمستخدم الأدمن"""
    from .models import Permission, Role, RolePermission, User, PermissionEnum
    
    # إنشاء الصلاحيات الافتراضية
    resources_actions = {
        "PersonDetail": ["view", "update", "delete"],
        "NewPerson": ["view"],
        "Users": ["view"],
        "Roles": ["view"],
        "Permissions": ["view"],
        "Settings": ["view"],
        "Reports": ["create"],
        "ActivityLogs": ["view"],
    }
    
    logger.info("جاري إعداد الصلاحيات الافتراضية...")
    for resource, actions in resources_actions.items():
        for action in actions:
            exists = session.query(Permission).filter_by(
                resource=resource, 
                action=PermissionEnum[action]
            ).first()
            if not exists:
                perm = Permission(resource=resource, action=PermissionEnum[action])
                session.add(perm)
                logger.info(f"✓ تم إنشاء الصلاحية: {resource}:{action}")
    
    session.commit()
    
    # إنشاء دور الأدمن
    logger.info("جاري إعداد دور الأدمن...")
    admin_role = session.query(Role).filter_by(name="Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin")
        session.add(admin_role)
        session.commit()
        logger.info("✓ تم إنشاء دور الأدمن")
    
    # إضافة جميع الصلاحيات للدور الأدمن
    permissions = session.query(Permission).all()
    for perm in permissions:
        exists = session.query(RolePermission).filter_by(
            role_id=admin_role.id, 
            permission_id=perm.id
        ).first()
        if not exists:
            session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))
    
    session.commit()
    logger.info(f"✓ تم إضافة {len(permissions)} صلاحية للدور الأدمن")
    
    # إنشاء مستخدم الأدمن الافتراضي
    logger.info("جاري إعداد مستخدم الأدمن...")
    admin_user = session.query(User).filter_by(username="admin").first()
    if not admin_user:
        admin_user = User(
            name="المسؤول",
            username="admin",
            password=hash_password("admin123"),
            is_superuser=True,
            role_id=admin_role.id
        )
        session.add(admin_user)
        session.commit()
        logger.info("✓ تم إنشاء حساب الأدمن (المستخدم: admin، كلمة المرور: admin123)")
    
    logger.info("✅ تم إنشاء جميع الصلاحيات والأدوار والحسابات بنجاح")

def apply_schema_updates(engine):
    """تطبيق تحديثات هيكلية خفيفة على القواعد الحالية دون الحاجة لإعادة ضبط القاعدة."""
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        with engine.begin() as conn:
            if "guardian_transactions" in table_names:
                columns = {col.get("name") for col in inspector.get_columns("guardian_transactions")}
                if "orphan_id" not in columns:
                    conn.execute(text("ALTER TABLE guardian_transactions ADD COLUMN orphan_id INTEGER"))
                    logger.info("✓ تمت إضافة العمود guardian_transactions.orphan_id")

                if "deceased_transaction_id" not in columns:
                    conn.execute(text("ALTER TABLE guardian_transactions ADD COLUMN deceased_transaction_id INTEGER"))
                    logger.info("✓ تمت إضافة العمود guardian_transactions.deceased_transaction_id")

                if "row_group_key" not in columns:
                    conn.execute(text("ALTER TABLE guardian_transactions ADD COLUMN row_group_key VARCHAR(255)"))
                    logger.info("✓ تمت إضافة العمود guardian_transactions.row_group_key")

                try:
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_guardian_transactions_orphan_id "
                            "ON guardian_transactions (orphan_id)"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_guardian_transactions_deceased_transaction_id "
                            "ON guardian_transactions (deceased_transaction_id)"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_guardian_transactions_row_group_key "
                            "ON guardian_transactions (row_group_key)"
                        )
                    )
                except Exception:
                    pass

            if "transactions" in table_names:
                t_columns = {col.get("name") for col in inspector.get_columns("transactions")}
                if "row_group_key" not in t_columns:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN row_group_key VARCHAR(255)"))
                    logger.info("✓ تمت إضافة العمود transactions.row_group_key")
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_transactions_row_group_key "
                            "ON transactions (row_group_key)"
                        )
                    )
                except Exception:
                    pass

            if "deceased_transactions" in table_names:
                d_columns = {col.get("name") for col in inspector.get_columns("deceased_transactions")}
                if "is_auto_manual_distribution" not in d_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE deceased_transactions "
                            "ADD COLUMN is_auto_manual_distribution BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                    logger.info("✓ تمت إضافة العمود deceased_transactions.is_auto_manual_distribution")
                if "row_group_key" not in d_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE deceased_transactions "
                            "ADD COLUMN row_group_key VARCHAR(255)"
                        )
                    )
                    logger.info("✓ تمت إضافة العمود deceased_transactions.row_group_key")
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_deceased_transactions_is_auto_manual_distribution "
                            "ON deceased_transactions (is_auto_manual_distribution)"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_deceased_transactions_row_group_key "
                            "ON deceased_transactions (row_group_key)"
                        )
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"تعذر تطبيق تحديثات هيكل القاعدة تلقائياً: {e}")

def initialize_database():
    """
    تهيئة قاعدة البيانات.
    تحاول الاتصال بـ MySQL، وإذا فشلت تستخدم SQLite كخيار احتياطي.
    تقوم أيضاً بإنشاء جميع الجداول والصلاحيات والأدوار والحسابات.
    """
    
    if test_mysql_connection():
        logger.info("استخدام قاعدة بيانات MySQL")
        engine = create_engine(MYSQL_DATABASE_URL, echo=False, pool_pre_ping=True)
        database_type = "MySQL"
    else:
        logger.warning("استخدام قاعدة بيانات SQLite كخيار احتياطي")
        engine = create_engine(SQLITE_DATABASE_URL, echo=False)
        database_type = "SQLite"
    
    # إنشاء جميع الجداول
    logger.info("جاري إنشاء الجداول...")
    Base.metadata.create_all(engine)
    logger.info("✓ تم إنشاء الجداول بنجاح")
    apply_schema_updates(engine)
    
    # إعداد الصلاحيات والأدوار والحسابات
    SessionLocal_temp = sessionmaker(bind=engine)
    session = SessionLocal_temp()
    try:
        setup_default_permissions_and_roles(session)
    finally:
        session.close()
    
    return engine, database_type

# ملاحظة: لا ننفّذ تهيئة قاعدة البيانات عند استيراد الوحدة لتجنّب
# دوائر الاستيراد (modules importing each other). استدعِ `initialize_database()`
# صراحة للحصول على `engine` و`DATABASE_TYPE` عند الحاجة.

engine = None
DATABASE_TYPE = None
SessionLocal = None

def get_session_local():
    global SessionLocal
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return SessionLocal