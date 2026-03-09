"""سكربت إنشاء مستخدم المسؤول والصلاحيات الافتراضية."""
import os
import sys

# إضافة جذر المشروع إلى المسار لتسهيل الاستيراد
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from sqlalchemy.orm import sessionmaker
import database.models  # register models
from database.models import User, Role, Permission, RolePermission, PermissionEnum
from database.db import initialize_database, Base


def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


engine, db_type = initialize_database()
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

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

for resource, actions in resources_actions.items():
    for action in actions:
        exists = db.query(Permission).filter_by(resource=resource, action=action).first()
        if not exists:
            perm = Permission(resource=resource, action=action)
            db.add(perm)

db.commit()

admin_role = db.query(Role).filter_by(name="Admin").first()
if not admin_role:
    admin_role = Role(name="Admin")
    db.add(admin_role)
    db.commit()

permissions = db.query(Permission).all()
for perm in permissions:
    exists = db.query(RolePermission).filter_by(role_id=admin_role.id, permission_id=perm.id).first()
    if not exists:
        db.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))

db.commit()

admin_user = db.query(User).filter_by(username="admin").first()
if not admin_user:
    admin_user = User(
        name="المسؤول",
        username="admin",
        password=hash_password("admin123"),
        is_superuser=True,
        role_id=admin_role.id
    )
    db.add(admin_user)
    db.commit()

db.close()
print("✅ All permissions, the Admin role, and the Admin user have been successfully created.")
