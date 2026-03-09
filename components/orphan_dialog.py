from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QComboBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QDate
from datetime import datetime
from sqlalchemy.orm import Session

# استبدل هذا بالـ Session الخاص بك
from database.db import SessionLocal
from database.models import Orphan, GenderEnum

class EditOrphanDialog(QDialog):
    def __init__(self, orphan_id, parent=None):
        super().__init__(parent)
        self.orphan_id = orphan_id
        self.db: Session = SessionLocal()

        self.setWindowTitle("تعديل بيانات اليتيم")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(400)

        self.build_ui()
        self.load_data()

    def build_ui(self):
        # Form Layout
        form = QFormLayout()

        # الاسم (إجباري)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("الاسم")
        form.addRow("الاسم *", self.name_edit)

        # رقم الهوية (إجباري)
        self.nid_edit = QLineEdit()
        self.nid_edit.setPlaceholderText("رقم الهوية")
        form.addRow("رقم الهوية *", self.nid_edit)

        # تاريخ الميلاد (إجباري) - LineEdit + InputMask
        self.birth_date_edit = QLineEdit()
        self.birth_date_edit.setPlaceholderText("DD/MM/YYYY")
        self.birth_date_edit.setInputMask("00/00/0000")
        form.addRow("تاريخ الميلاد *", self.birth_date_edit)

        # الجنس (إجباري)
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["ذكر", "أنثى"])
        form.addRow("الجنس *", self.gender_combo)

        # رقم الجوال (اختياري)
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("05xxxxxxxx")
        form.addRow("رقم الجوال", self.phone_edit)

        # رقم الحساب (اختياري)
        self.account_edit = QLineEdit()
        form.addRow("رقم الحساب", self.account_edit)

        # رقم الأرشيف (اختياري)
        self.archives_edit = QLineEdit()
        form.addRow("رقم الأرشيف", self.archives_edit)

        # أزرار حفظ وإلغاء
        btn_save = QPushButton("حفظ")
        btn_cancel = QPushButton("إلغاء")
        btn_save.clicked.connect(self.on_save)
        btn_cancel.clicked.connect(self.reject)

        btns_layout = QHBoxLayout()
        btns_layout.addStretch()
        btns_layout.addWidget(btn_cancel)
        btns_layout.addWidget(btn_save)

        # Layout رئيسي
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btns_layout)

    def load_data(self):
        orphan: Orphan = self.db.get(Orphan, self.orphan_id)
        if not orphan:
            QMessageBox.warning(self, "خطأ", "اليتيم غير موجود!")
            self.reject()
            return

        self.name_edit.setText(orphan.name)
        self.nid_edit.setText(orphan.national_id or "")
        self.birth_date_edit.setText(
            orphan.date_birth.strftime("%d/%m/%Y") if orphan.date_birth else ""
        )
        self.gender_combo.setCurrentIndex(0 if orphan.gender == GenderEnum.male else 1)
        self.phone_edit.setText(orphan.phone or "")
        self.account_edit.setText(orphan.deceased.account_number if orphan.deceased else "")
        self.archives_edit.setText(orphan.deceased.archives_number if orphan.deceased else "")

    def parse_date(self, text: str):
        try:
            return datetime.strptime(text, "%d/%m/%Y").date()
        except ValueError:
            return None

    def validate_required_fields(self):
        required_fields = {
            "الاسم": self.name_edit.text().strip(),
            "رقم الهوية": self.nid_edit.text().strip(),
            "تاريخ الميلاد": self.birth_date_edit.text().strip(),
            "الجنس": self.gender_combo.currentText(),
        }

        missing = [label for label, value in required_fields.items() if not value]

        if missing:
            QMessageBox.warning(
                self,
                "حقول ناقصة",
                "الحقول التالية إجبارية:\n" + "\n".join(missing)
            )
            return False

        # تحقق من صحة التاريخ
        birth_date = self.parse_date(self.birth_date_edit.text().strip())
        if not birth_date:
            QMessageBox.warning(self, "خطأ", "تاريخ الميلاد غير صحيح")
            return False

        return True

    def on_save(self):
        if not self.validate_required_fields():
            return

        orphan: Orphan = self.db.get(Orphan, self.orphan_id)
        if not orphan:
            QMessageBox.warning(self, "خطأ", "اليتيم غير موجود!")
            return

        # حفظ البيانات
        orphan.name = self.name_edit.text().strip()
        orphan.national_id = self.nid_edit.text().strip() or None
        orphan.date_birth = self.parse_date(self.birth_date_edit.text().strip()) if self.birth_date_edit.text().strip() else None
        orphan.gender = GenderEnum.male if self.gender_combo.currentIndex() == 0 else GenderEnum.female
        orphan.phone = self.phone_edit.text().strip() or None

        # حفظ رقم الحساب ورقم الأرشيف في المتوفي المرتبط إذا موجود
        if orphan.deceased:
            orphan.deceased.account_number = self.account_edit.text().strip() or None
            orphan.deceased.archives_number = self.archives_edit.text().strip() or None

        self.db.commit()
        QMessageBox.information(self, "نجاح", "تم حفظ التعديلات بنجاح.")
        self.accept()
