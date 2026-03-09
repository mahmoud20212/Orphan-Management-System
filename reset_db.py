"""سكربت إعادة تعيين قاعدة البيانات."""
import os
import sys
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from database.models import Currency

# إضافة جذر المشروع إلى المسار
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def add_default_currencies(session: Session):
    default_list = [
        {"code": "ILS", "name": "شيكل"},
        {"code": "USD", "name": "دولار أمريكي"},
        {"code": "EUR", "name": "يورو"},
        {"code": "JOD", "name": "دينار أردني"}
    ]

    for cur in default_list:
        if not session.query(Currency).filter_by(code=cur["code"]).first():
            session.add(Currency(code=cur["code"], name=cur["name"]))
    session.commit()


try:
    # تأكد من استيراد النماذج أولاً لتسجيلها لدى Base
    import database.models  # registers models with Base
    from database.db import initialize_database, Base
    engine, db_type = initialize_database()
except ImportError as e:
    print("-------------------------------------------------------------------")
    print("Import Error:")
    print("Please ensure 'database/db.py' and 'models.py' are in the correct path.")
    print(f"Error: {e}")
    print("-------------------------------------------------------------------")
    sys.exit(1)


def reset_database():
    print("-------------------------------------------------------------------")
    print("Starting database reset process...")

    try:
        print("1. Dropping all tables...")
        Base.metadata.drop_all(engine)
        print("All tables dropped successfully.")

        print("2. Creating all tables...")
        Base.metadata.create_all(engine)
        print("All tables created successfully.")

        print("3. Adding default currencies...")
        session = Session(bind=engine)
        add_default_currencies(session)
        session.close()
        print("Default currencies added successfully.")

        print("-------------------------------------------------------------------")
        print("Database reset completed successfully.")
        print("-------------------------------------------------------------------")

    except OperationalError as e:
        print("-------------------------------------------------------------------")
        print("Connection or Operational Error:")
        print("Please ensure the database is running and connection details in database/db.py are correct.")
        print(f"Error: {e}")
        print("-------------------------------------------------------------------")
    except Exception as e:
        print("-------------------------------------------------------------------")
        print(f"An unexpected error occurred: {e}")
        print("-------------------------------------------------------------------")


if __name__ == "__main__":
    reset_database()
