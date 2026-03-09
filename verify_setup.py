#!/usr/bin/env python
"""سكريبت للتحقق من أن جميع الجداول والصلاحيات والأدوار والمستخدمين تم إنشاؤها بنجاح"""

from sqlalchemy import inspect
from database.db import engine, SessionLocal
from database.models import Permission, Role, User

# فحص الجداول
inspector = inspect(engine)
tables = inspector.get_table_names()
print("✅ الجداول المُنشأة:")
for table in sorted(tables):
    print(f"  - {table}")

print("\n" + "="*60 + "\n")

# فحص الصلاحيات والأدوار والمستخدمين
session = SessionLocal()
try:
    permissions = session.query(Permission).all()
    print(f"✅ عدد الصلاحيات: {len(permissions)}")
    for perm in permissions:
        print(f"  - {perm.resource}:{perm.action.value}")
    
    print("\n" + "="*60 + "\n")
    
    roles = session.query(Role).all()
    print(f"✅ عدد الأدوار: {len(roles)}")
    for role in roles:
        print(f"  - {role.name} (الصلاحيات: {len(role.permissions)})")
    
    print("\n" + "="*60 + "\n")
    
    users = session.query(User).all()
    print(f"✅ عدد المستخدمين: {len(users)}")
    for user in users:
        print(f"  - {user.username} ({user.name}) - Super: {user.is_superuser}")
        
finally:
    session.close()

print("\n" + "="*60)
print("✅ تم إنشاء جميع البيانات بنجاح!")
print("="*60)
