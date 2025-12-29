import os
import sys
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from models import Currency

# Add current path to sys.path to ensure local modules are imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
    # database/connection.py must contain the definition of engine and Base
    from database import Base
    from database.connection import engine
    # All models must be imported to ensure Base.metadata knows about them
    # We assume models.py contains all table definitions
    import models 
except ImportError as e:
    print("-------------------------------------------------------------------")
    print("Import Error:")
    print("Please ensure 'database/connection.py' and 'models.py' are in the correct path.")
    print(f"Error: {e}")
    print("-------------------------------------------------------------------")
    sys.exit(1)

def reset_database():
    """
    Drops all tables, recreates them, and adds default currencies.
    """
    print("-------------------------------------------------------------------")
    print("Starting database reset process...")

    try:
        # 1. Drop all tables
        print("1. Dropping all tables...")
        Base.metadata.drop_all(engine)
        print("All tables dropped successfully.")

        # 2. Create all tables
        print("2. Creating all tables...")
        Base.metadata.create_all(engine)
        print("All tables created successfully.")

        # 3. Add default currencies
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
        print("Please ensure the database is running and connection details in database/connection.py are correct.")
        print(f"Error: {e}")
        print("-------------------------------------------------------------------")
    except Exception as e:
        print("-------------------------------------------------------------------")
        print(f"An unexpected error occurred: {e}")
        print("-------------------------------------------------------------------")


if __name__ == "__main__":
    reset_database()