import pytest
import sys
import os
# ensure project root is importable during pytest collection
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from repositories.db_repository import DBService
from database.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    return SessionLocal


@pytest.fixture
def db_service(in_memory_db):
    svc = DBService()
    svc.get_db = lambda: in_memory_db()
    return svc


def test_add_transaction_updates_balance(db_service):
    db = db_service.get_db()
    from models.currency import Currency
    from models.orphan import Orphan

    cur = Currency(code="NIS", name="NIS")
    orphan = Orphan(name="Test Orphan", national_id="NID-001")
    db.add(cur)
    db.add(orphan)
    db.commit()

    tx_id = db_service.add_transaction(orphan.id, {
        "currency": "NIS",
        "amount": 100,
        "type": "إيداع",
        "date": datetime.now(),
        "note": "initial deposit"
    })

    assert isinstance(tx_id, int)

    balances = db_service.get_orphan_balances(orphan.id)
    assert len(balances) == 1
    assert float(balances[0].balance) == pytest.approx(100.0)


def test_update_transaction_adjusts_balance(db_service):
    db = db_service.get_db()
    from models.currency import Currency
    from models.orphan import Orphan

    cur = Currency(code="NIS", name="NIS")
    db.add(cur)
    orphan = Orphan(name="Test Orphan 2", national_id="NID-002")
    db.add(orphan)
    db.commit()

    tx_id = db_service.add_transaction(orphan.id, {
        "currency": "NIS",
        "amount": 100,
        "type": "إيداع",
        "date": datetime.now(),
        "note": "deposit"
    })

    # update: turn deposit 100 into withdrawal 50
    updated = db_service.update_transaction({
        "id": tx_id,
        "currency": "NIS",
        "amount": 50,
        "type": "سحب",
        "date": datetime.now(),
        "note": "changed"
    })
    assert updated is True

    balances = db_service.get_orphan_balances(orphan.id)
    # original +100, now -50 => total -50
    assert len(balances) == 1
    assert float(balances[0].balance) == pytest.approx(-50.0)


def test_delete_transaction_reverses_balance(db_service):
    db = db_service.get_db()
    from models.currency import Currency
    from models.orphan import Orphan

    cur = Currency(code="NIS", name="NIS")
    db.add(cur)
    orphan = Orphan(name="Test Orphan 3", national_id="NID-003")
    db.add(orphan)
    db.commit()

    tx_id = db_service.add_transaction(orphan.id, {
        "currency": "NIS",
        "amount": 80,
        "type": "إيداع",
        "date": datetime.now(),
        "note": "deposit"
    })

    deleted = db_service.delete_transaction(tx_id)
    assert deleted is True

    balances = db_service.get_orphan_balances(orphan.id)
    # balance should be 0 after reversal
    assert len(balances) == 1
    assert float(balances[0].balance) == pytest.approx(0.0)


def test_add_deceased_and_orphans_creates_records(db_service):
    db = db_service.get_db()
    deceased_data = {"name": "Deceased A", "national_id": "D-001", "date_of_death": datetime.now()}
    guardian_data = {"name": "Guard A", "national_id": "G-001", "phone": "012345"}
    orphans_data = [
        {"name": "Child 1", "national_id": "C-001"},
        {"name": "Child 2", "national_id": "C-002"}
    ]

    result = db_service.add_deceased_and_orphans(deceased_data, guardian_data, orphans_data)
    assert result is True

    # verify created
    deceased, orphans, guardian = db_service.get_deceased_details(1)
    assert deceased is not None
    assert guardian is not None
    assert len(orphans) == 2


def test_get_minors_count_by_month(db_service):
    from models.orphan import Orphan
    from datetime import date, datetime, timedelta

    db = db_service.get_db()

    today = date.today()
    # compute first day of current month and a day in previous month
    first_day_curr = date(today.year, today.month, 1)
    prev_month_last = first_day_curr - timedelta(days=1)
    prev_month_mid = date(prev_month_last.year, prev_month_last.month, min(10, prev_month_last.day))
    curr_month_mid = date(today.year, today.month, min(10, 28))

    # Orphan A: minor, created in previous month -> counted in prev and current
    orphan_a = Orphan(name="A", national_id="A-001", date_of_birth=date(today.year - 10, 1, 1), created_at=datetime(prev_month_mid.year, prev_month_mid.month, prev_month_mid.day, 12, 0))
    # Orphan B: minor, created in current month -> counted only in current
    orphan_b = Orphan(name="B", national_id="B-001", date_of_birth=date(today.year - 5, 1, 1), created_at=datetime(curr_month_mid.year, curr_month_mid.month, curr_month_mid.day, 12, 0))
    # Orphan C: adult, created in previous month -> not counted
    orphan_c = Orphan(name="C", national_id="C-001", date_of_birth=date(today.year - 30, 1, 1), created_at=datetime(prev_month_mid.year, prev_month_mid.month, prev_month_mid.day, 12, 0))

    db.add_all([orphan_a, orphan_b, orphan_c])
    db.commit()

    res = db_service.get_minors_count_by_month(2)  # returns [(prev_label, prev_count), (curr_label, curr_count)]
    assert len(res) == 2
    prev_label, prev_count = res[0]
    curr_label, curr_count = res[1]
    assert prev_count == 1  # only orphan_a was minor by prev month-end
    assert curr_count == 2  # orphan_a + orphan_b
