from decimal import Decimal
from datetime import datetime, timezone, date, time
from uuid import uuid4
import database.db as db_module
from database.models import ActivityLog, DeceasedBalance, DeceasedTransaction, GuardianBalance, GuardianTransaction, Orphan, Guardian, Deceased, Currency, TransactionTypeEnum, OrphanGuardian, GenderEnum, OrphanBalance, Transaction
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import case, or_, text, func

from utils import parse_and_validate_date
from utils.helpers import try_get_date
from utils.notes_generator import generate_transaction_note, generate_deceased_transaction_note, generate_orphan_transaction_note
from utils.distribution import calculate_beneficiary_distribution

# ===== DB Service =====
class DBService:
    def __init__(self):
        # Ensure the database engine and SessionLocal are initialized.
        try:
            session_factory = db_module.SessionLocal
        except Exception:
            session_factory = None

        if not session_factory:
            # Initialize DB (creates engine and tables) and set SessionLocal
            engine, db_type = db_module.initialize_database()
            db_module.engine = engine
            db_module.DATABASE_TYPE = db_type
            from sqlalchemy.orm import sessionmaker
            db_module.SessionLocal = sessionmaker(bind=engine)
            session_factory = db_module.SessionLocal

        self.session = session_factory()

    def close(self):
        self.session.close()

    def find_by_national_id(self, nid):
        orphan = (
            self.session.query(Orphan)
            .filter(Orphan.national_id == nid)
            .first()
        )

        guardian = self.session.query(Guardian).filter(
            Guardian.national_id == nid
        ).first()

        deceased = self.session.query(Deceased).filter(
            Deceased.national_id == nid
        ).first()

        return orphan, guardian, deceased

    def find_by_archive_number(self, archive_num):
        return self.session.query(Deceased).filter(
            Deceased.archive_number == archive_num
        ).first()

    def find_by_archive_or_id(self, term):
        # Try national_id first (for backward compatibility)
        orphan_id = self.session.query(Orphan).filter(Orphan.national_id == term).first()
        guardian_id = self.session.query(Guardian).filter(Guardian.national_id == term).first()
        deceased_id = self.session.query(Deceased).filter(Deceased.national_id == term).first()
        # If not found by national_id, try by name
        if not orphan_id:
            orphan_id = self.session.query(Orphan).filter(Orphan.name.ilike(term)).first()
        if not guardian_id:
            guardian_id = self.session.query(Guardian).filter(Guardian.name.ilike(term)).first()
        if not deceased_id:
            deceased_id = self.session.query(Deceased).filter(Deceased.name.ilike(term)).first()
        # Also try archive number
        deceased_arc = self.session.query(Deceased).filter(Deceased.archives_number == term).first()
        return orphan_id, guardian_id, deceased_id, deceased_arc

    def _create_opening_balances(self, db, orphan_id: int, balances: dict, create_transactions: bool = False, note=None, transaction_details: dict = None):
        if not balances:
            return
        currencies = {c.code: c.id for c in db.query(Currency).all()}
        for currency_code, amount in balances.items():
            amount_dec = Decimal(amount)
            if amount_dec == Decimal(0):
                continue
            if amount_dec < 0:
                raise ValueError("لا يمكن أن يكون الرصيد الافتتاحي سالبًا")
            currency_id = currencies.get(currency_code)
            if not currency_id:
                raise ValueError(f"العملة {currency_code} غير معرفة في النظام")
            existing_balance = db.query(OrphanBalance).filter_by(orphan_id=orphan_id, currency_id=currency_id).first()
            if existing_balance:
                continue
            db.add(OrphanBalance(orphan_id=orphan_id, currency_id=currency_id, balance=amount_dec))
            if create_transactions:
                details = (transaction_details or {}).get(currency_code, {}) if isinstance(transaction_details, dict) else {}
                payment_method = (details.get("payment_method") or "").strip() or None
                if payment_method in ("اختر", "---"):
                    payment_method = None

                due_date_raw = try_get_date(details.get("due_date"))
                due_date = parse_and_validate_date(due_date_raw) if due_date_raw else None

                db.add(Transaction(
                    orphan_id=orphan_id,
                    currency_id=currency_id,
                    type=TransactionTypeEnum.deposit,
                    amount=amount_dec,
                    created_date=datetime.now(timezone.utc),
                    note=note,
                    document_number=(details.get("document_number") or "").strip() or None,
                    person_name=(details.get("person_name") or "").strip() or None,
                    payment_method=payment_method,
                    check_number=(details.get("check_number") or "").strip() or None,
                    due_date=due_date,
                    bank_name=(details.get("bank_name") or "").strip() or None,
                    reference_number=(details.get("reference_number") or "").strip() or None,
                ))

    def add_deceased_and_orphans(self, deceased_data: dict, guardian_data: dict, orphans_data: list, all_currencies_details: dict, selected_mode: str):
        db = self.session
        try:
            # orphans_check = db.query(Orphan).all()
            # if len(orphans_check) > 5:
            #     raise ValueError('لقد تجاوزت الحد المسموح به')
            row_group_key = f"grp_{uuid4().hex}"
            deceased = Deceased(**deceased_data)
            db.add(deceased)
            db.flush()
            relation_to_orphans = guardian_data.pop('relation', "غير محدد")
            start_date_val = guardian_data.pop('start_date', datetime.now().date())
            # Find guardian by name (name is now unique)
            guardian = db.query(Guardian).filter_by(name=guardian_data['name']).first()
            if not guardian:
                guardian = Guardian(**guardian_data)
                db.add(guardian)
                db.flush()
            total_increments = {"ILS": Decimal('0'), "USD": Decimal('0'), "JOD": Decimal('0'), "EUR": Decimal('0')}
            orphan_transactions_to_link = {"ILS": [], "USD": [], "JOD": [], "EUR": []}
            for o_dict in orphans_data:
                o_dict.pop('relation', None)
                o_dict.pop('start_date', None)
                o_dict.pop('guardian_name', None)
                o_dict.pop('guardian_national_id', None)
                o_dict.pop('is_primary', None)
                for c in ["ils", "usd", "jod", "eur"]:
                    o_dict.pop(f'original_{c}_balance', None)
                target_balances = {"ILS": Decimal(str(o_dict.pop('ils_balance', 0))), "USD": Decimal(str(o_dict.pop('usd_balance', 0))), "JOD": Decimal(str(o_dict.pop('jod_balance', 0))), "EUR": Decimal(str(o_dict.pop('eur_balance', 0)))}
                # Find orphan by name (name is now unique) instead of national_id
                orphan = db.query(Orphan).filter_by(name=o_dict['name']).first()
                if orphan:
                    for key, value in o_dict.items():
                        if hasattr(orphan, key): setattr(orphan, key, value)
                    orphan.deceased_id = deceased.id
                else:
                    orphan = Orphan(deceased_id=deceased.id, **o_dict)
                    db.add(orphan)
                db.flush()
                for code, new_total in target_balances.items():
                    currency = db.query(Currency).filter_by(code=code).first()
                    if not currency: continue
                    bal_obj = db.query(OrphanBalance).filter_by(orphan_id=orphan.id, currency_id=currency.id).first()
                    old_val = bal_obj.balance if bal_obj else Decimal('0')
                    increment = new_total - old_val
                    if increment > 0:
                        total_increments[code] += increment
                        note_text = generate_transaction_note('orphan_share', {
                            'deceased_name': deceased.name,
                            'orphan_name': orphan.name,
                            'currency': code,
                            'amount': increment
                        })
                        new_o_trans = Transaction(orphan_id=orphan.id, currency_id=currency.id, amount=increment, type=TransactionTypeEnum.deposit, note=note_text, row_group_key=row_group_key)
                        orphan_transactions_to_link[code].append(new_o_trans)
                    if bal_obj:
                        bal_obj.balance = new_total
                    else:
                        db.add(OrphanBalance(orphan_id=orphan.id, currency_id=currency.id, balance=new_total))
                db.query(OrphanGuardian).filter_by(orphan_id=orphan.id, is_primary=True).update({"is_primary": False, "end_date": datetime.now().date()})
                db.add(OrphanGuardian(orphan_id=orphan.id, guardian_id=guardian.id, is_primary=True, relation=relation_to_orphans, start_date=start_date_val))
            for code, info in all_currencies_details.items():
                amount_input = Decimal(str(info.get('amount', 0)))
                distributed = total_increments.get(code, Decimal('0'))
                if amount_input <= 0 and distributed <= 0: continue
                currency = db.query(Currency).filter_by(code=code).first()
                if not currency: continue
                if amount_input > 0:
                    note_text = generate_deceased_transaction_note(
                        'deposit',
                        amount_input,
                        currency.name,
                        distribution_mode=selected_mode,
                        receipt_details=info
                    )
                    db.add(DeceasedTransaction(deceased_id=deceased.id, currency_id=currency.id, amount=amount_input, type=TransactionTypeEnum.deposit, receipt_number=info.get('receipt_number'), payer_name=info.get('payer_name'), payment_method=info.get('payment_method') if info.get('payment_method') != 'اختر' else None, check_number=info.get('check_number'), due_date=parse_and_validate_date(info.get('due_date')) if info.get('due_date') else None, bank_name=info.get('bank_name'), reference_number=info.get('reference_number'), note=note_text, row_group_key=row_group_key))
                if distributed > 0:
                    note_text = generate_deceased_transaction_note(
                        'distribute',
                        distributed,
                        currency.name,
                        distribution_mode=selected_mode
                    )
                    deceased_withdraw_txn = DeceasedTransaction(deceased_id=deceased.id, currency_id=currency.id, amount=distributed, type=TransactionTypeEnum.withdraw, payment_method=None, note=note_text, row_group_key=row_group_key)
                    db.add(deceased_withdraw_txn)
                    db.flush()
                    for o_trans in orphan_transactions_to_link[code]:
                        o_trans.deceased_transaction_id = deceased_withdraw_txn.id
                        db.add(o_trans)
                db.add(DeceasedBalance(deceased_id=deceased.id, currency_id=currency.id, balance=amount_input - distributed))
            db.commit()
            return {'deceased_id': deceased.id}
        except Exception as e:
            db.rollback()
            print(f"Database Error: {e}")
            raise e

    def get_currencies(self):
        return self.session.query(Currency).all()

    def get_deceased_people_list(self):
        db = self.session
        return db.query(Deceased, func.count(Orphan.id).label("orphans_count")).outerjoin(Orphan, Deceased.id == Orphan.deceased_id).group_by(Deceased.id).all()

    def get_guardians_list(self):
        db = self.session
        return db.query(Guardian, func.count(OrphanGuardian.orphan_id.distinct()).label("orphans_count")).outerjoin(OrphanGuardian, Guardian.id == OrphanGuardian.guardian_id).group_by(Guardian.id).all()

    def get_orphans_list(self):
        return self.session.query(Orphan).outerjoin(OrphanGuardian).options(joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian)).all()

    def get_orphans_older_than_or_equal_18_list(self):
        today = date.today()
        cutoff_date = date(today.year - 18, today.month, today.day)
        return self.session.query(Orphan).filter(Orphan.date_birth <= cutoff_date).all()

    def paginate(self, query, page: int = 1, per_page: int = 20):
        total = query.count()
        items = query.limit(per_page).offset((page - 1) * per_page).all()
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": (total + per_page - 1) // per_page}

    def get_deceased_people_paginated(self, page=1, per_page=20):
        query = self.session.query(Deceased, func.count(Orphan.id).label("orphans_count")).outerjoin(Orphan, Deceased.id == Orphan.deceased_id).group_by(Deceased.id).order_by(Deceased.id.desc())
        return self.paginate(query, page, per_page)

    def get_guardians_paginated(self, page=1, per_page=20):
        query = self.session.query(Guardian, func.count(OrphanGuardian.orphan_id.distinct()).label("orphans_count")).outerjoin(OrphanGuardian, Guardian.id == OrphanGuardian.guardian_id).group_by(Guardian.id).order_by(Guardian.id.desc())
        return self.paginate(query, page, per_page)

    def get_orphans_paginated(self, page=1, per_page=20):
        query = self.session.query(Orphan).outerjoin(OrphanGuardian).options(joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian)).order_by(Orphan.id.desc())
        return self.paginate(query, page, per_page)

    def get_orphans_older_than_or_equal_18_paginated(self, page=1, per_page=20):
        today = date.today()
        cutoff_date = date(today.year - 18, today.month, today.day)
        query = self.session.query(Orphan).filter(Orphan.date_birth <= cutoff_date).order_by(Orphan.id.desc())
        return self.paginate(query, page, per_page)

    def get_activity_logs_paginated(self, page=1, per_page=20):
        query = self.session.query(ActivityLog).order_by(ActivityLog.id.desc())
        return self.paginate(query, page, per_page)

    def get_summary_counts(self):
        db = self.session
        total_orphans = db.query(func.count(Orphan.id)).scalar() or 0
        today = date.today()
        cutoff = date(today.year - 18, today.month, today.day)
        # Only count orphans where date_birth is not NULL and is <= cutoff
        orphans_over_18 = db.query(func.count(Orphan.id)).filter(Orphan.date_birth != None, Orphan.date_birth <= cutoff).scalar() or 0
        total_guardians = db.query(func.count(Guardian.id)).scalar() or 0
        total_deceased = db.query(func.count(Deceased.id)).scalar() or 0
        return {"orphans": int(total_orphans), "orphans_over_18": int(orphans_over_18), "guardians": int(total_guardians), "deceased": int(total_deceased)}

    def search_guardian(self, text):
        return self.session.query(Guardian).filter(or_(Guardian.national_id.ilike(f"%{text}%"), Guardian.name.ilike(f"%{text}%"))).limit(20).all()

    def search_deceased(self, text):
        return self.session.query(Deceased).filter(or_(Deceased.national_id.ilike(f"%{text}%"), Deceased.name.ilike(f"%{text}%"))).limit(20).all()

    def search_orphan(self, text, _all=False, linked=False):
        query = self.session.query(Orphan)
        if not _all:
            query = query.filter(Orphan.deceased_id == None) if linked is False else query.filter(Orphan.deceased_id != None)
        return query.filter(or_(Orphan.national_id.ilike(f"%{text}%"), Orphan.name.ilike(f"%{text}%"))).limit(20).all()

    def check_if_orphan_exists(self, name: str) -> bool:
        """Check if orphan exists by NAME (primary key for duplicates)"""
        return self.session.query(Orphan).filter(Orphan.name == name).first() is not None

    def get_orphan_by_name(self, name):
        """Get orphan by NAME (primary lookup)"""
        return self.session.query(Orphan).filter_by(name=name).first()

    def get_orphan_by_national_id(self, national_id):
        """Legacy: Get orphan by national_id (may return multiple, use with caution)"""
        return self.session.query(Orphan).filter_by(national_id=national_id).first()

    def check_if_deceased_exists(self, name: str) -> bool:
        """Check if deceased exists by NAME (primary key for duplicates)"""
        return self.session.query(Deceased).filter(Deceased.name == name).first() is not None

    def get_deceased_by_name(self, name):
        """Get deceased by NAME (primary lookup)"""
        return self.session.query(Deceased).filter_by(name=name).first()

    def check_if_guardian_exists(self, name: str) -> bool:
        """Check if guardian exists by NAME (primary key for duplicates)"""
        return self.session.query(Guardian).filter(Guardian.name == name).first() is not None

    def get_guardian_by_name(self, name):
        """Get guardian by NAME (primary lookup)"""
        return self.session.query(Guardian).filter_by(name=name).first()

    def get_orphan_details(self, orphan_id: int):
        return self.session.query(Orphan).options(joinedload(Orphan.deceased), joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian), joinedload(Orphan.balances).joinedload(OrphanBalance.currency)).filter(Orphan.id == orphan_id).first()

    def get_deceased_details(self, deceased_id: int):
        deceased = self.session.query(Deceased).options(joinedload(Deceased.orphans).joinedload(Orphan.balances).joinedload(OrphanBalance.currency)).filter(Deceased.id == deceased_id).first()
        guardian = None
        if deceased and deceased.orphans:
            primary_link = self.session.query(OrphanGuardian).filter_by(orphan_id=deceased.orphans[0].id, is_primary=True).first()
            if primary_link:
                guardian = primary_link.guardian
        return deceased, (deceased.orphans if deceased else []), guardian

    def get_guardian_details(self, guardian_id: int):
        guardian = self.session.query(Guardian).filter_by(id=guardian_id).first()
        if not guardian:
            return None, []
        orphans = self.session.query(Orphan).join(OrphanGuardian).options(joinedload(Orphan.balances).joinedload(OrphanBalance.currency)).filter(OrphanGuardian.guardian_id == guardian_id).all()
        return guardian, orphans

    def get_orphan_balances(self, orphan_id: int):
        return self.session.query(OrphanBalance).options(joinedload(OrphanBalance.currency)).filter_by(orphan_id=orphan_id).all()

    def get_orphan_transactions(self, orphan_id: int, limit: int = 15):
        return self.session.query(Transaction).options(joinedload(Transaction.currency)).filter_by(orphan_id=orphan_id).order_by(Transaction.created_date.desc()).limit(limit).all()

    def get_orphans_by_date_range(self, start_dt, end_dt):
        end_dt_full = datetime.combine(end_dt.date(), time.max)
        return self.session.query(Orphan).options(joinedload(Orphan.balances).joinedload(OrphanBalance.currency), joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian)).filter(Orphan.created_at >= start_dt).filter(Orphan.created_at <= end_dt_full).all()

    def add_single_deceased_transaction(self, data):
        session = self.session
        try:
            should_distribute = data.pop('should_distribute', False)
            dist_mode = data.pop('distribution_mode', "بالتساوي")
            include_guardian_share = data.pop('include_guardian_share', False)
            new_txn = DeceasedTransaction(**data)
            session.add(new_txn)
            self._update_deceased_balance(session, data['deceased_id'], data['currency_id'], data['amount'], data['type'])
            if should_distribute:
                orphans = session.query(Orphan).filter_by(deceased_id=data['deceased_id']).all()
                if not orphans:
                    raise ValueError("لا يوجد أيتام مسجلون لتوزيع المبلغ عليهم.")

                beneficiaries = [
                    {
                        "kind": "orphan",
                        "id": o.id,
                        "gender": o.gender,
                        "name": o.name,
                    }
                    for o in orphans
                ]

                guardian_for_share = None
                guardian_link_for_share = None
                if include_guardian_share:
                    guardian_link_for_share = self._get_primary_guardian_link_for_deceased(session, data['deceased_id'])
                    guardian_for_share = guardian_link_for_share.guardian if guardian_link_for_share else None
                    if guardian_for_share:
                        beneficiaries.append({
                            "kind": "guardian",
                            "id": guardian_for_share.id,
                            "gender": None,
                            "name": guardian_for_share.name,
                        })

                shares = self._calculate_shares(beneficiaries, data['amount'], dist_mode)
                linked_user_note = (data.get('note') or '').strip() or None
                auto_distribution_note = f"توزيع ({dist_mode}) - المبلغ الموزع: {Decimal(str(data['amount'])):,.2f}"
                if data['type'] == 'deposit':
                    withdraw_txn = DeceasedTransaction(
                        deceased_id=data['deceased_id'],
                        currency_id=data['currency_id'],
                        amount=data['amount'],
                        type='withdraw',
                        payment_method=data['payment_method'],
                        note=auto_distribution_note,
                    )
                    session.add(withdraw_txn)
                    self._update_deceased_balance(session, data['deceased_id'], data['currency_id'], data['amount'], 'withdraw')
                    session.flush()
                    parent_txn_id = withdraw_txn.id
                else:
                    session.flush()
                    parent_txn_id = new_txn.id

                for beneficiary in beneficiaries:
                    share_amount = Decimal(str(shares.get((beneficiary['kind'], beneficiary['id']), 0)))
                    if share_amount <= 0: continue

                    if beneficiary['kind'] == 'orphan':
                        new_orphan_txn = Transaction(
                            orphan_id=beneficiary['id'],
                            currency_id=data['currency_id'],
                            amount=share_amount,
                            type=TransactionTypeEnum.deposit,
                            deceased_transaction_id=parent_txn_id,
                            created_date=datetime.now(timezone.utc),
                            note=linked_user_note,
                        )
                        session.add(new_orphan_txn)
                        self._update_orphan_balance(session, beneficiary['id'], data['currency_id'], share_amount)
                    else:
                        new_guardian_txn = GuardianTransaction(
                            guardian_id=beneficiary['id'],
                            deceased_id=data['deceased_id'],
                            currency_id=data['currency_id'],
                            deceased_transaction_id=parent_txn_id,
                            amount=share_amount,
                            type=TransactionTypeEnum.deposit,
                            created_date=datetime.now(timezone.utc),
                            created_at=datetime.now(timezone.utc),
                            note=linked_user_note,
                        )
                        session.add(new_guardian_txn)
                        self._update_guardian_balance(session, beneficiary['id'], data['currency_id'], share_amount)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error: {e}")
            return False

    def _build_distribution_note(self, base_note, beneficiaries, shares, mode: str):
        base = (base_note or "").strip()
        beneficiary_chunks = []
        for beneficiary in beneficiaries:
            key = (beneficiary.get('kind'), beneficiary.get('id'))
            amount = Decimal(str(shares.get(key, 0)))
            if amount <= 0:
                continue

            if beneficiary.get('kind') == 'guardian':
                label = f"الوصي {beneficiary.get('name') or ''}".strip()
            else:
                label = beneficiary.get('name') or f"يتيم {beneficiary.get('id')}"
            beneficiary_chunks.append(f"{label}: {amount:,.2f}")

        details = f"تفاصيل التوزيع ({mode}): "
        details += "، ".join(beneficiary_chunks) if beneficiary_chunks else "لا توجد حصص"

        final_note = f"{base} | {details}" if base else details
        return final_note[:250]

    def _update_orphan_balance(self, session, orphan_id, currency_id, amount):
        bal = session.query(OrphanBalance).filter_by(orphan_id=orphan_id, currency_id=currency_id).first()
        if bal:
            bal.balance += amount
        else:
            session.add(OrphanBalance(orphan_id=orphan_id, currency_id=currency_id, balance=amount))

    def _update_guardian_balance(self, session, guardian_id, currency_id, amount):
        bal = session.query(GuardianBalance).filter_by(guardian_id=guardian_id, currency_id=currency_id).first()
        if bal:
            bal.balance += amount
        else:
            session.add(GuardianBalance(guardian_id=guardian_id, currency_id=currency_id, balance=amount))

    def _get_primary_guardian_for_deceased(self, session, deceased_id):
        primary_link = self._get_primary_guardian_link_for_deceased(session, deceased_id)
        return primary_link.guardian if primary_link else None

    def _get_primary_guardian_link_for_deceased(self, session, deceased_id):
        primary_link = (
            session.query(OrphanGuardian)
            .join(Orphan, Orphan.id == OrphanGuardian.orphan_id)
            .filter(Orphan.deceased_id == deceased_id, OrphanGuardian.is_primary == True)
            .first()
        )
        if primary_link:
            return primary_link

        any_link = (
            session.query(OrphanGuardian)
            .join(Orphan, Orphan.id == OrphanGuardian.orphan_id)
            .filter(Orphan.deceased_id == deceased_id)
            .first()
        )
        return any_link

    def _update_deceased_balance(self, session, deceased_id, currency_id, amount, txn_type):
        balance_record = session.query(DeceasedBalance).filter_by(deceased_id=deceased_id, currency_id=currency_id).first()
        is_deposit = (txn_type == 'deposit')
        if balance_record:
            balance_record.balance += amount if is_deposit else -amount
            balance_record.updated_at = datetime.now()
        else:
            session.add(DeceasedBalance(deceased_id=deceased_id, currency_id=currency_id, balance=amount if is_deposit else -amount))

    def _calculate_shares(self, beneficiaries, total_amount, mode):
        return calculate_beneficiary_distribution(beneficiaries, total_amount, mode)

    def get_deceased_balance(self, deceased_id, currency_code):
        try:
            result = self.session.query(DeceasedBalance.balance).join(Currency).filter(DeceasedBalance.deceased_id == deceased_id, Currency.code == currency_code).first()
            return result[0] if result else Decimal('0.00')
        except Exception as e:
            print(f"خطأ أثناء جلب الرصيد: {e}")
            return Decimal('0.00')
    
    def get_deceased_summary(self, deceased_id):
        session = self.session
        # استعلام لجلب إجمالي الإيداعات والسحوبات من جدول العمليات
        transactions = session.query(
            DeceasedTransaction.currency_id,
            func.sum(case((DeceasedTransaction.type == TransactionTypeEnum.deposit, DeceasedTransaction.amount), else_=0)).label('total_deposit'),
            func.sum(case((DeceasedTransaction.type == TransactionTypeEnum.withdraw, DeceasedTransaction.amount), else_=0)).label('total_withdraw')
        ).filter(DeceasedTransaction.deceased_id == deceased_id).group_by(DeceasedTransaction.currency_id).subquery()

        # الربط مع جدول العملات وجدول الأرصدة الحالي
        results = session.query(
            Currency.name,
            func.coalesce(transactions.c.total_deposit, 0).label('deposited'),
            func.coalesce(transactions.c.total_withdraw, 0).label('withdrawn'),
            func.coalesce(DeceasedBalance.balance, 0).label('available')
        ).outerjoin(
            DeceasedBalance,
            (DeceasedBalance.currency_id == Currency.id) & (DeceasedBalance.deceased_id == deceased_id)
        )\
        .outerjoin(transactions, transactions.c.currency_id == Currency.id)\
        .all()

        return results
    
    def get_orphan_summary(self, orphan_id):
        session = self.session
        # حساب العمليات (إيداع/سحب)
        transactions = session.query(
            Transaction.currency_id,
            func.sum(case((Transaction.type == TransactionTypeEnum.deposit, Transaction.amount), else_=0)).label('total_deposit'),
            func.sum(case((Transaction.type == TransactionTypeEnum.withdraw, Transaction.amount), else_=0)).label('total_withdraw')
        ).filter(Transaction.orphan_id == orphan_id).group_by(Transaction.currency_id).subquery()

        # الاستعلام النهائي للجدول
        results = session.query(
            Currency.name,
            func.coalesce(transactions.c.total_deposit, 0).label('deposited'),
            func.coalesce(transactions.c.total_withdraw, 0).label('withdrawn'),
            func.coalesce(OrphanBalance.balance, 0).label('available')
        ).outerjoin(
            OrphanBalance,
            (OrphanBalance.currency_id == Currency.id) & (OrphanBalance.orphan_id == orphan_id)
        )\
        .outerjoin(transactions, transactions.c.currency_id == Currency.id)\
        .all()

        return results
    
    def get_guardian_summary(self, guardian_id):
        session = self.session
        transactions = session.query(
            GuardianTransaction.currency_id,
            func.sum(case((GuardianTransaction.type == TransactionTypeEnum.deposit, GuardianTransaction.amount), else_=0)).label('total_deposit'),
            func.sum(case((GuardianTransaction.type == TransactionTypeEnum.withdraw, GuardianTransaction.amount), else_=0)).label('total_withdraw')
        ).filter(GuardianTransaction.guardian_id == guardian_id).group_by(GuardianTransaction.currency_id).subquery()
        
        results = session.query(
            Currency.name,
            func.coalesce(transactions.c.total_deposit, 0).label('deposited'),
            func.coalesce(transactions.c.total_withdraw, 0).label('withdrawn'),
            func.coalesce(GuardianBalance.balance, 0).label('available')
        ).outerjoin(
            GuardianBalance,
            (GuardianBalance.currency_id == Currency.id) & (GuardianBalance.guardian_id == guardian_id)
        )\
        .outerjoin(transactions, transactions.c.currency_id == Currency.id)\
        .all()
        
        return results

    def search_deceased_in_db(self, search_term):
        """البحث في قاعدة البيانات بناءً على الاسم أو الهوية أو الأرشيف"""
        session = self.session
        
        if not search_term or len(search_term) < 2:
            return []
        
        # البحث باستخدام OR لجمع كافة الاحتمالات
        results = session.query(Deceased).filter(
            or_(
                Deceased.name.like(f"%{search_term}%"),
                Deceased.national_id.like(f"%{search_term}%"),
                Deceased.archives_number.like(f"%{search_term}%")
            )
        ).limit(15).all() # تحديد عدد النتائج لسرعة الاستجابة
        return results