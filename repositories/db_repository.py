from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, func
from database.connection import SessionLocal
from models import Deceased, Orphan, OrphanGuardian, Guardian
from datetime import date

from models.currency import Currency
from models.orphan_balance import OrphanBalance
from models.transaction import Transaction

class DBService:
    """
    Database Service / Repository
    This class contains all DB access logic. It is intended to be imported from
    application modules as `from repositories.db_repository import DBService`.
    """
    def __init__(self):
        pass

    def get_db(self) -> Session:
        return SessionLocal()

    def test_connection(self) -> bool:
        try:
            db = self.get_db()
            result = db.execute(text("SELECT 1")).fetchone()
            db.close()
            return result[0] == 1
        except Exception:
            return False

    # Common read and utility methods migrated from the previous implementation
    def load_deceaseds_with_orphan_count(self):
        """Fetches the list of deceased persons with the count of their orphans."""
        db = self.get_db()
        try:
            deceaseds = (
                db.query(
                    Deceased,
                    func.count(Orphan.id).label("orphans_count")
                )
                .outerjoin(Orphan, Deceased.id == Orphan.deceased_id)
                .group_by(Deceased.id)
                .all()
            )
            return deceaseds
        finally:
            db.close()

    def load_guardians_with_orphan_count(self):
        """Fetches the list of guardians with the count of their associated orphans."""
        db = self.get_db()
        try:
            guardians = (
                db.query(
                    Guardian,
                    func.count(OrphanGuardian.orphan_id.distinct()).label("orphans_count")
                )
                .outerjoin(OrphanGuardian, Guardian.id == OrphanGuardian.guardian_id)
                .group_by(Guardian.id)
                .all()
            )
            return guardians
        finally:
            db.close()

    def load_all_orphans(self):
        """Fetch all orphans from the database with guardian link preloads."""
        db = self.get_db()
        try:
            orphans = (
                db.query(Orphan)
                .outerjoin(OrphanGuardian)
                .options(
                    joinedload(Orphan.guardian_links)
                    .joinedload(OrphanGuardian.guardian)
                )
                .all()
            )
            return orphans
        finally:
            db.close()

    def get_deceased_details(self, deceased_id: int):
        """Fetches details of the deceased, its orphans, and the primary guardian."""
        db = self.get_db()
        try:
            deceased = db.query(Deceased).filter_by(id=deceased_id).first()
            if not deceased:
                return None, None, None

            orphans = (
                db.query(Orphan)
                .options(
                    joinedload(Orphan.deceased),
                    joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian)
                )
                .filter_by(deceased_id=deceased_id)
                .all()
            )

            # Attempt to fetch a primary guardian (if any) for the first orphan
            if orphans:
                primary_guardian_link = (
                    db.query(OrphanGuardian)
                    .join(Guardian)
                    .filter(OrphanGuardian.orphan_id == orphans[0].id,
                            OrphanGuardian.is_primary == True)
                    .first()
                )
                guardian = primary_guardian_link.guardian if primary_guardian_link else None
            else:
                guardian = None

            return deceased, orphans, guardian
        finally:
            db.close()

    def get_orphan_details(self, orphan_id: int):
        """Fetch an orphan with preloaded relations (deceased, guardian links)."""
        db = self.get_db()
        try:
            orphan = (
                db.query(Orphan)
                .options(
                    joinedload(Orphan.guardian_links)
                    .joinedload(OrphanGuardian.guardian),
                    joinedload(Orphan.deceased)
                )
                .filter(Orphan.id == orphan_id)
                .first()
            )
            return orphan
        finally:
            db.close()

    def search_by_national_id(self, national_id: str):
        """Search for orphan/guardian/deceased by national id."""
        db = self.get_db()
        try:
            orphan = db.query(Orphan).filter(Orphan.national_id == national_id).options(
                joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian)
            ).first()

            guardian = db.query(Guardian).filter(Guardian.national_id == national_id).first()

            deceased = db.query(Deceased).filter(Deceased.national_id == national_id).first()

            return {"orphan": orphan, "guardian": guardian, "deceased": deceased}
        finally:
            db.close()

    def get_orphans_count_by_month(self, months: int = 12):
        """Return a list of (label, count) for the last `months` months (oldest first)."""
        db = self.get_db()
        try:
            today = date.today()
            results = []
            for offset in range(months - 1, -1, -1):
                total_month = (today.year * 12 + today.month - 1) - offset
                year = total_month // 12
                month = total_month % 12 + 1
                first_day = date(year, month, 1)
                if month == 12:
                    next_month = date(year + 1, 1, 1)
                else:
                    next_month = date(year, month + 1, 1)

                count = db.query(func.count(Orphan.id)).filter(
                    Orphan.created_at >= first_day,
                    Orphan.created_at < next_month
                ).scalar() or 0

                label = f"{year}-{month:02d}"
                results.append((label, int(count)))
            return results
        finally:
            db.close()

    def get_minors_count_by_month(self, months: int = 12):
        """Return a list of (label, count) for the last `months` months counting orphans
        who were minors (under 18) at month-end and who were registered before month-end."""
        db = self.get_db()
        try:
            from datetime import timedelta
            today = date.today()
            results = []
            for offset in range(months - 1, -1, -1):
                total_month = (today.year * 12 + today.month - 1) - offset
                year = total_month // 12
                month = total_month % 12 + 1
                first_day = date(year, month, 1)
                if month == 12:
                    next_month = date(year + 1, 1, 1)
                else:
                    next_month = date(year, month + 1, 1)
                # month_end is the last day of the month
                month_end = next_month - timedelta(days=1)
                # cutoff date: anyone born after cutoff is under 18 at month_end
                try:
                    cutoff = date(month_end.year - 18, month_end.month, month_end.day)
                except ValueError:
                    # handle leap day fallback to day 28
                    cutoff = date(month_end.year - 18, month_end.month, 28)

                count = db.query(func.count(Orphan.id)).filter(
                    Orphan.created_at < next_month,
                    Orphan.date_of_birth != None,
                    Orphan.date_of_birth > cutoff
                ).scalar() or 0

                label = f"{year}-{month:02d}"
                results.append((label, int(count)))
            return results
        finally:
            db.close()

    def get_age_distribution(self, buckets=None):
        """Return age distribution counts for given buckets."""
        if buckets is None:
            buckets = [(0,5),(6,12),(13,17),(18,200)]

        db = self.get_db()
        try:
            rows = db.query(Orphan.date_of_birth).filter(Orphan.date_of_birth != None).all()
            ages = []
            today = date.today()
            for (dob,) in rows:
                if not dob:
                    continue
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                ages.append(age)

            distribution = []
            for (min_a, max_a) in buckets:
                cnt = sum(1 for a in ages if a is not None and a >= min_a and a <= max_a)
                if max_a >= 200:
                    label = f"{min_a}+"
                else:
                    label = f"{min_a}-{max_a}"
                distribution.append((label, cnt))

            return distribution
        finally:
            db.close()

    def get_summary_counts(self):
        """Return a dict with summary counts: orphans, orphans_over_18, guardians, deceased."""
        db = self.get_db()
        try:
            total_orphans = db.query(func.count(Orphan.id)).scalar() or 0

            today = date.today()
            cutoff = date(today.year - 18, today.month, today.day)
            orphans_over_18 = db.query(func.count(Orphan.id)).filter(
                Orphan.date_of_birth != None,
                Orphan.date_of_birth <= cutoff
            ).scalar() or 0

            total_guardians = db.query(func.count(Guardian.id)).scalar() or 0
            total_deceased = db.query(func.count(Deceased.id)).scalar() or 0

            return {
                "orphans": int(total_orphans),
                "orphans_over_18": int(orphans_over_18),
                "guardians": int(total_guardians),
                "deceased": int(total_deceased)
            }
        finally:
            db.close()

    def _apply_balance_change(self, db: Session, orphan_id: int, currency_id: int, amount_change):
        """Apply a signed Decimal amount_change to the orphan's balance for the given currency.
        Creates the OrphanBalance row if it does not exist."""
        from decimal import Decimal
        if amount_change is None:
            return
        try:
            change = Decimal(str(amount_change))
        except Exception:
            change = Decimal(0)

        ob = db.query(OrphanBalance).filter_by(orphan_id=orphan_id, currency_id=currency_id).first()
        if not ob:
            ob = OrphanBalance(orphan_id=orphan_id, currency_id=currency_id, balance=change)
            db.add(ob)
        else:
            # Ensure Decimal arithmetic
            ob.balance = (ob.balance or 0) + change
        # Note: commit should be handled by caller

    def get_orphan_balances(self, orphan_id: int):
        db = self.get_db()
        try:
            balances = (
                db.query(OrphanBalance)
                .options(joinedload(OrphanBalance.currency))
                .filter(OrphanBalance.orphan_id == orphan_id)
                .all()
            )
            return balances
        finally:
            db.close()

    def get_orphan_transactions(self, orphan_id: int):
        """
        Fetch all transactions for a specific orphan,
        including currency name and transaction type as text.
        """
        db = self.get_db()
        try:
            transactions = (
                db.query(Transaction)
                .options(joinedload(Transaction.currency))
                .filter(Transaction.orphan_id == orphan_id)
                .order_by(Transaction.transaction_date.desc())
                .all()
            )

            # تحويل البيانات إلى قائمة dicts لسهولة العرض
            result = []
            for t in transactions:
                result.append({
                    "id": t.id,
                    "currency": t.currency.name if t.currency else "",
                    "amount": float(t.amount),
                    "type": "إيداع" if t.transaction_type == 1 else "سحب",
                    "date": t.transaction_date,
                    "note": t.note or ""
                })
            return result
        finally:
            db.close()

    def get_currency_names(self):
        """Return list of Currency objects ordered by name."""
        db = self.get_db()
        try:
            currencies = db.query(Currency).order_by(Currency.name).all()
            return currencies
        finally:
            db.close()

    def get_guardian_details(self, guardian_id: int):
        """Fetches details of a specific guardian and all associated orphans.

        Eager-load related objects (e.g., deceased) so the caller can access them
        after the DB session is closed without triggering lazy-load errors.
        """
        db = self.get_db()
        try:
            guardian = db.query(Guardian).filter_by(id=guardian_id).first()
            if not guardian:
                return None, None

            # جلب الأيتام المرتبطين بهذا الوصي مع التحميل المسبق للمتوفّى
            orphans = (
                db.query(Orphan)
                .options(
                    joinedload(Orphan.deceased),
                    joinedload(Orphan.guardian_links).joinedload(OrphanGuardian.guardian)
                )
                .join(OrphanGuardian, Orphan.id == OrphanGuardian.orphan_id)
                .filter(OrphanGuardian.guardian_id == guardian_id)
                .all()
            )

            return guardian, orphans
        finally:
            db.close()

    def update_guardian_and_orphans(self, guardian_id: int, guardian_data: dict):
        """
        Updates guardian details in a single transaction.
        
        Args:
            guardian_id: The ID of the guardian to update.
            guardian_data: Dictionary containing updated guardian data.
        """
        db = self.get_db()
        try:
            # 1. Update Guardian Details
            # Check for duplicate national_id, excluding the current guardian
            if 'national_id' in guardian_data:
                existing_guardian = (
                    db.query(Guardian)
                    .filter(Guardian.national_id == guardian_data['national_id'])
                    .filter(Guardian.id != guardian_id)
                    .first()
                )
                if existing_guardian:
                    raise ValueError(f"National ID {guardian_data['national_id']} is already registered for another guardian.")

            db.query(Guardian).filter_by(id=guardian_id).update(guardian_data)

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def delete_guardian(self, guardian_id: int):
        """
        Deletes a guardian record safely.
        Orphans are NOT deleted.
        Only orphan-guardian links are removed first.
        """
        db = self.get_db()
        try:
            # 1️⃣ حذف روابط الوصي مع الأيتام
            db.query(OrphanGuardian).filter(
                OrphanGuardian.guardian_id == guardian_id
            ).delete(synchronize_session=False)

            # 2️⃣ حذف الوصي نفسه
            deleted = db.query(Guardian).filter(
                Guardian.id == guardian_id
            ).delete()

            if deleted == 0:
                raise Exception("الوصي غير موجود")

            db.commit()
            return True

        except Exception as e:
            db.rollback()
            raise e

        finally:
            db.close()

    def add_deceased_and_orphans(self, deceased_data: dict, guardian_data: dict, orphans_data: list):
        """
        Adds a new deceased person, guardian, and their associated orphans in a single transaction.
        """
        db = self.get_db()
        try:
            # 1. التحقق من التكرار
            if db.query(Deceased).filter_by(national_id=deceased_data['national_id']).first():
                raise ValueError("Deceased person's national ID already exists.")
            if db.query(Guardian).filter_by(national_id=guardian_data['national_id']).first():
                raise ValueError("Guardian's national ID already exists.")

            # 2. إنشاء المتوفى
            deceased = Deceased(**deceased_data)
            db.add(deceased)
            db.flush() # للحصول على deceased.id

            # 3. إنشاء الوصي
            guardian = Guardian(**guardian_data)
            db.add(guardian)
            db.flush() # للحصول على guardian.id

            # 4. إنشاء الأيتام وربطهم بالوصي
            for orphan_data in orphans_data:
                orphan = Orphan(
                    deceased_id=deceased.id,
                    **orphan_data
                )
                db.add(orphan)
                db.flush() # للحصول على orphan.id

                # ربط الوصي
                link = OrphanGuardian(
                    orphan_id=orphan.id,
                    guardian_id=guardian.id,
                    is_primary=True,
                    start_date=date.today()
                )
                db.add(link)

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def update_deceased_and_orphans(self, deceased_id: int, deceased_data: dict, guardian_data: dict, orphans_data: list):
        """
        Updates data for a deceased person, guardian, and their associated orphans in a single transaction.
        """
        db = self.get_db()
        try:
            deceased = db.query(Deceased).filter_by(id=deceased_id).first()
            if not deceased:
                raise ValueError(f"Deceased person with ID {deceased_id} not found.")

            for key, value in deceased_data.items():
                setattr(deceased, key, value)

            current_orphans = db.query(Orphan).filter_by(deceased_id=deceased_id).all()
            primary_guardian_link = None

            if current_orphans:
                primary_guardian_link = (
                    db.query(OrphanGuardian)
                    .join(Guardian)
                    .filter(OrphanGuardian.orphan_id == current_orphans[0].id,
                            OrphanGuardian.is_primary == True)
                    .first()
                )

            if primary_guardian_link:
                guardian = primary_guardian_link.guardian
                new_national_id = guardian_data.get('national_id')
                if new_national_id and new_national_id != guardian.national_id:
                    existing_guardian = db.query(Guardian).filter(
                        Guardian.national_id == new_national_id,
                        Guardian.id != guardian.id
                    ).first()
                    if existing_guardian:
                        raise ValueError("The new guardian's national ID already exists for another guardian.")

                for key, value in guardian_data.items():
                    setattr(guardian, key, value)
            else:
                # If no primary guardian exists, we skip guardian update here
                pass

            existing_orphan_ids = {o.id for o in current_orphans}
            updated_orphan_ids = set()

            for orphan_data in orphans_data:
                orphan_id = orphan_data.pop('id', None)
                if orphan_id and orphan_id in existing_orphan_ids:
                    orphan = db.query(Orphan).filter_by(id=orphan_id).first()
                    if orphan:
                        for key, value in orphan_data.items():
                            setattr(orphan, key, value)
                        updated_orphan_ids.add(orphan_id)
                elif not orphan_id:
                    orphan = Orphan(
                        deceased_id=deceased_id,
                        **orphan_data
                    )
                    db.add(orphan)
                    db.flush()
                    if primary_guardian_link:
                        link = OrphanGuardian(
                            orphan_id=orphan.id,
                            guardian_id=primary_guardian_link.guardian_id,
                            is_primary=True,
                            start_date=date.today()
                        )
                        db.add(link)

            orphans_to_delete_ids = existing_orphan_ids - updated_orphan_ids
            if orphans_to_delete_ids:
                db.query(OrphanGuardian).filter(OrphanGuardian.orphan_id.in_(orphans_to_delete_ids)).delete(synchronize_session=False)
                db.query(Orphan).filter(Orphan.id.in_(orphans_to_delete_ids)).delete(synchronize_session=False)

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def delete_deceased(self, deceased_id: int):
        """Deletes a deceased person, all associated orphans and links, and the guardian if no longer linked to any other orphan."""
        db = self.get_db()
        try:
            orphans = db.query(Orphan).filter_by(deceased_id=deceased_id).all()
            orphan_ids = [o.id for o in orphans]

            guardian_to_check = None
            if orphan_ids:
                primary_link = db.query(OrphanGuardian).filter(
                    OrphanGuardian.orphan_id == orphan_ids[0],
                    OrphanGuardian.is_primary == True
                ).first()
                if primary_link:
                    guardian_to_check = primary_link.guardian

            if orphan_ids:
                db.query(Transaction).filter(Transaction.orphan_id.in_(orphan_ids)).delete(synchronize_session=False)
                db.query(OrphanBalance).filter(OrphanBalance.orphan_id.in_(orphan_ids)).delete(synchronize_session=False)
                db.query(OrphanGuardian).filter(OrphanGuardian.orphan_id.in_(orphan_ids)).delete(synchronize_session=False)
                db.query(Orphan).filter(Orphan.id.in_(orphan_ids)).delete(synchronize_session=False)

            db.query(Deceased).filter_by(id=deceased_id).delete()

            if guardian_to_check:
                remaining_links = db.query(OrphanGuardian).filter(OrphanGuardian.guardian_id == guardian_to_check.id).count()
                if remaining_links == 0:
                    db.delete(guardian_to_check)

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def update_orphan_basic_data(self, orphan_id: int, orphan_data: dict):
        db = self.get_db()
        try:
            orphan = db.query(Orphan).filter(Orphan.id == orphan_id).first()
            if not orphan:
                raise ValueError("اليتيم غير موجود")

            for key, value in orphan_data.items():
                setattr(orphan, key, value)

            db.commit()
            return True

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def add_transaction(self, orphan_id: int, transaction_data: dict):
        db = self.get_db()
        from decimal import Decimal
        try:
            currency = db.query(Currency).filter(
                Currency.name == transaction_data["currency"]
            ).first()

            if not currency:
                raise ValueError("العملة غير موجودة")

            amount = Decimal(str(transaction_data["amount"]))
            tx_type = 1 if transaction_data["type"] == "إيداع" else 2

            transaction = Transaction(
                orphan_id=orphan_id,
                currency_id=currency.id,
                amount=amount,
                transaction_type=tx_type,
                transaction_date=transaction_data["date"],
                note=transaction_data.get("note")
            )

            db.add(transaction)

            effect = amount if tx_type == 1 else -amount
            self._apply_balance_change(db, orphan_id, currency.id, effect)

            db.commit()
            return transaction.id

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def update_transaction(self, transaction_data: dict):
        db = self.get_db()
        from decimal import Decimal
        try:
            transaction = db.query(Transaction).filter(
                Transaction.id == transaction_data["id"]
            ).first()

            if not transaction:
                raise ValueError("العملية غير موجودة")

            old_amount = Decimal(str(transaction.amount))
            old_type = transaction.transaction_type
            old_currency_id = transaction.currency_id

            new_currency = db.query(Currency).filter(
                Currency.name == transaction_data["currency"]
            ).first()

            if not new_currency:
                raise ValueError("العملة غير موجودة")

            new_amount = Decimal(str(transaction_data["amount"]))
            new_type = 1 if transaction_data["type"] == "إيداع" else 2

            old_effect = old_amount if old_type == 1 else -old_amount
            new_effect = new_amount if new_type == 1 else -new_amount

            if old_currency_id != new_currency.id:
                self._apply_balance_change(db, transaction.orphan_id, old_currency_id, -old_effect)
                self._apply_balance_change(db, transaction.orphan_id, new_currency.id, new_effect)
            else:
                delta = new_effect - old_effect
                self._apply_balance_change(db, transaction.orphan_id, new_currency.id, delta)

            transaction.currency_id = new_currency.id
            transaction.amount = new_amount
            transaction.transaction_type = new_type
            transaction.transaction_date = transaction_data["date"]
            transaction.note = transaction_data.get("note")

            db.commit()
            return True

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def delete_transaction(self, transaction_id: int):
        """Deletes a transaction and reverses its effect on the orphan's balance."""
        db = self.get_db()
        from decimal import Decimal
        try:
            transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
            if not transaction:
                raise ValueError("العملية غير موجودة")

            amount = Decimal(str(transaction.amount))
            effect = amount if transaction.transaction_type == 1 else -amount

            self._apply_balance_change(db, transaction.orphan_id, transaction.currency_id, -effect)

            db.delete(transaction)
            db.commit()
            return True

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def update_orphan_and_transactions(
        self,
        orphan_id: int,
        orphan_data: dict,
        transactions_data: list
    ):
        db = self.get_db()
        from decimal import Decimal
        try:
            # 1️⃣ تحديث بيانات اليتيم
            orphan = db.query(Orphan).filter(Orphan.id == orphan_id).first()
            if not orphan:
                raise ValueError("اليتيم غير موجود")

            for key, value in orphan_data.items():
                setattr(orphan, key, value)

            # 2️⃣ إضافة أو تعديل العمليات
            for trx in transactions_data:
                currency = db.query(Currency).filter(
                    Currency.name == trx["currency"]
                ).first()
                if not currency:
                    raise ValueError("عملة غير موجودة")

                if trx.get("id"):  # تعديل
                    transaction = db.query(Transaction).filter(
                        Transaction.id == trx["id"]
                    ).first()
                    if not transaction:
                        raise ValueError("عملية غير موجودة")

                    old_amount = Decimal(str(transaction.amount))
                    old_type = transaction.transaction_type
                    old_currency_id = transaction.currency_id
                    old_effect = old_amount if old_type == 1 else -old_amount

                    new_amount = Decimal(str(trx["amount"]))
                    new_type = 1 if trx["type"] == "إيداع" else 2
                    new_effect = new_amount if new_type == 1 else -new_amount

                    if old_currency_id != currency.id:
                        self._apply_balance_change(db, orphan_id, old_currency_id, -old_effect)
                        self._apply_balance_change(db, orphan_id, currency.id, new_effect)
                    else:
                        delta = new_effect - old_effect
                        self._apply_balance_change(db, orphan_id, currency.id, delta)

                    transaction.currency_id = currency.id
                    transaction.amount = new_amount
                    transaction.transaction_type = new_type
                    transaction.transaction_date = trx["date"]
                    transaction.note = trx.get("note")

                else:  # إضافة
                    amount = Decimal(str(trx["amount"]))
                    tx_type = 1 if trx["type"] == "إيداع" else 2
                    transaction = Transaction(
                        orphan_id=orphan_id,
                        currency_id=currency.id,
                        amount=amount,
                        transaction_type=tx_type,
                        transaction_date=trx["date"],
                        note=trx.get("note")
                    )
                    db.add(transaction)

                    effect = amount if tx_type == 1 else -amount
                    self._apply_balance_change(db, orphan_id, currency.id, effect)

            db.commit()
            return True

        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def load_orphans_older_than_or_equal_18(self):
        db = self.get_db()
        try:
            today = date.today()
            cutoff_date = date(today.year - 18, today.month, today.day)

            return (
                db.query(Orphan)
                .filter(Orphan.date_of_birth <= cutoff_date)
                .all()
            )

        except Exception as e:
            print("Error loading orphans older than 18:", e)
            return []
        finally:
            db.close()
