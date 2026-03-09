from sqlalchemy import or_
import sys
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QLineEdit, QListWidget,
    QLabel, QRadioButton, QButtonGroup, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox, QFormLayout,
    QComboBox, QDoubleSpinBox, QDateEdit, QWidget, QDialogButtonBox, QCheckBox, QGridLayout, QScrollArea
)
from PyQt6.QtCore import Qt, QDate, QLocale, QTimer
from decimal import Decimal
from database.models import Deceased, Orphan
from services.reporting import generate_monthly_report

class GuardianSearchDialog(QDialog):
    def __init__(self, db_service, parent=None):
        super().__init__(parent)
        self.db_service = db_service
        self.selected_person = None
        self.setWindowTitle("بحث عن وصي")
        self.resize(450, 350)

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ادخل الاسم أو رقم الهوية...")
        self.search_input.setStyleSheet("padding: 8px; font-size: 14px; border: 1px solid #3498db; border-radius: 4px;")
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.results_list.setStyleSheet("""
            QListWidget::item { padding: 10px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #3498db; color: white; }
        """)
        layout.addWidget(self.results_list)

        self.search_input.textChanged.connect(self.update_results)
        self.results_list.itemDoubleClicked.connect(self.accept_selection)
        self.current_results = []

    def update_results(self, text):
        self.results_list.clear()
        if len(text) < 2: return
        
        # البحث في قاعدة البيانات
        self.current_results = self.db_service.search_guardian(text)
        
        for guardian in self.current_results:
            self.results_list.addItem(f"{guardian.name} | رقم الهوية: {guardian.national_id or '---'}")

    def accept_selection(self):
        index = self.results_list.currentRow()
        if index >= 0:
            self.selected_person = self.current_results[index]
            self.accept()


class DeceasedSearchDialog(QDialog):
    def __init__(self, db_service, parent=None):
        super().__init__(parent)
        self.db_service = db_service
        self.selected_person = None
        self.setWindowTitle("بحث عن متوفى")
        self.resize(450, 350)

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ادخل الاسم أو رقم الهوية...")
        self.search_input.setStyleSheet("padding: 8px; font-size: 14px; border: 1px solid #3498db; border-radius: 4px;")
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.results_list.setStyleSheet("""
            QListWidget::item { padding: 10px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #3498db; color: white; }
        """)
        layout.addWidget(self.results_list)

        self.search_input.textChanged.connect(self.update_results)
        self.results_list.itemDoubleClicked.connect(self.accept_selection)
        self.current_results = []

    def update_results(self, text):
        self.results_list.clear()
        if len(text) < 2: return
        
        # البحث في قاعدة البيانات
        self.current_results = self.db_service.search_deceased(text)
        
        for deceased in self.current_results:
            self.results_list.addItem(f"{deceased.name} | رقم الهوية: {deceased.national_id or '---'}")

    def accept_selection(self):
        index = self.results_list.currentRow()
        if index >= 0:
            self.selected_person = self.current_results[index]
            self.accept()

class OrphanSearchDialog(QDialog):
    def __init__(self, db_service, parent=None, file_type='', exclude_ids=None):
        super().__init__(parent)
        self.db_service = db_service
        self.selected_orphan = None
        self.file_type = file_type
        self.exclude_ids = set(exclude_ids) if exclude_ids else set()
        
        self.setWindowTitle("البحث عن يتيم")
        self.resize(500, 400)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)

        if self.file_type == 'deceased':
            label = QLabel("ملاحظة: يظهر فقط الأيتام غير المرتبطين بملف متوفي مسبقاً.")
            label.setStyleSheet("color: #e74c3c; font-size: 13px; font-weight: bold;")
            layout.addWidget(label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ادخل الاسم أو رقم الهوية...")
        self.search_input.setStyleSheet("padding: 8px; font-size: 14px; border: 1px solid #3498db; border-radius: 4px;")
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.setStyleSheet("""
            QListWidget::item { padding: 10px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #3498db; color: white; }
        """)
        layout.addWidget(self.results_list)

        self.search_input.textChanged.connect(self.update_results)
        self.results_list.itemDoubleClicked.connect(self.accept_selection)
        self.current_results = []

    def update_results(self, text):
        self.results_list.clear()
        search_text = text.strip()
        if len(search_text) < 2: return
        
        # جلب النتائج بناءً على نوع الملف
        if self.file_type == 'deceased':
            raw_results = self.db_service.search_orphan(search_text)
        else:
            raw_results = self.db_service.search_orphan(search_text, _all=True)
        
        # استبعاد المعرفات الموجودة في الجدول حالياً
        self.current_results = [o for o in raw_results if o.id not in self.exclude_ids]
        
        for orphan in self.current_results:
            self.results_list.addItem(f"{orphan.name} | رقم الهوية: {orphan.national_id or '---'}")

    def accept_selection(self):
        index = self.results_list.currentRow()
        if index >= 0:
            self.selected_orphan = self.current_results[index]
            self.accept()

class ExportReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تصدير تقرير دوري")
        self.setFixedSize(350, 250)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # حقول التاريخ
        self.label_from = QLabel("من تاريخ:")
        self.date_from = QLineEdit()
        self.date_from.setInputMask("9999-99-99") # تنسيق YYYY-MM-DD
        self.date_from.setText(QDate.currentDate().addMonths(-1).toString("yyyy-MM-dd"))

        self.label_to = QLabel("إلى تاريخ:")
        self.date_to = QLineEdit()
        self.date_to.setInputMask("9999-99-99")
        self.date_to.setText(QDate.currentDate().toString("yyyy-MM-dd"))

        # اختيار نوع التصدير
        self.label_type = QLabel("نوع التصدير:")
        self.radio_pdf = QRadioButton("ملف PDF (رسمي)")
        self.radio_excel = QRadioButton("ملف Excel (بيانات)")
        self.radio_pdf.setChecked(True)

        self.group = QButtonGroup()
        self.group.addButton(self.radio_pdf)
        self.group.addButton(self.radio_excel)

        # أزرار العمليات
        btn_layout = QHBoxLayout()
        self.btn_export = QPushButton("تصدير الآن")
        self.btn_export.setProperty('class', 'btn btn-success')
        self.btn_export.clicked.connect(self.handle_export)
        
        self.btn_cancel = QPushButton("إلغاء")
        self.btn_cancel.setProperty('class', 'btn btn-danger')
        self.btn_cancel.clicked.connect(self.reject)

        # إضافة العناصر للواجهة
        layout.addWidget(self.label_from)
        layout.addWidget(self.date_from)
        layout.addWidget(self.label_to)
        layout.addWidget(self.date_to)
        layout.addWidget(self.label_type)
        
        radio_layout = QHBoxLayout()
        radio_layout.addWidget(self.radio_pdf)
        radio_layout.addWidget(self.radio_excel)
        layout.addLayout(radio_layout)
        
        btn_layout.addWidget(self.btn_export)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def validate_dates(self):
        """التحقق من صحة التواريخ المدخلة"""
        from_dt_str = self.date_from.text().strip()
        to_dt_str = self.date_to.text().strip()
        
        # التحقق من عدم ترك التواريخ فارغة
        if not from_dt_str or not to_dt_str:
            QMessageBox.warning(self, "خطأ", "يرجى إدخال التواريخ (من إلى)")
            return False
        
        # التحقق من صيغة التاريخ (YYYY-MM-DD)
        from_date = QDate.fromString(from_dt_str, "yyyy-MM-dd")
        to_date = QDate.fromString(to_dt_str, "yyyy-MM-dd")
        
        if not from_date.isValid():
            QMessageBox.warning(self, "خطأ في التاريخ", f"تاريخ البداية غير صحيح: {from_dt_str}\nالصيغة الصحيحة: يوم-شهر-سنة")
            self.date_from.setFocus()
            return False
        
        if not to_date.isValid():
            QMessageBox.warning(self, "خطأ في التاريخ", f"تاريخ النهاية غير صحيح: {to_dt_str}\nالصيغة الصحيحة: يوم-شهر-سنة")
            self.date_to.setFocus()
            return False
        
        # التحقق من أن تاريخ البداية لا يتجاوز تاريخ النهاية
        if from_date > to_date:
            QMessageBox.warning(self, "خطأ في النطاق الزمني", "تاريخ البداية لا يمكن أن يكون بعد تاريخ النهاية")
            self.date_from.setFocus()
            return False
        
        return True

    def handle_export(self):
        # التحقق من صحة التواريخ قبل البدء
        if not self.validate_dates():
            return
        
        from_dt = self.date_from.text()
        to_dt = self.date_to.text()
        is_pdf = self.radio_pdf.isChecked()
        format_type = "pdf" if is_pdf else "excel"
        
        # --- حل مشكلة الاسم الافتراضي ---
        extension = "pdf" if is_pdf else "xlsx"
        default_name = f"تقرير_الأيتام_الدوري_{from_dt}_إلى_{to_dt}.{extension}"
        
        # نمرر default_name كمعامل ثالث في الدالة أدناه
        path, _ = QFileDialog.getSaveFileName(
            self, 
            "حفظ التقرير", 
            default_name, 
            "PDF Files (*.pdf)" if is_pdf else "Excel Files (*.xlsx)"
        )

        if path:
            try:
                # التأكد من وصول الكائنات الصحيحة من الأب (Parent)
                db_service = self.parent().db_service
                user_name = self.parent().current_user.name
                
                generate_monthly_report(
                    from_dt, to_dt, path, 
                    db_service, 
                    user_name, 
                    format_type
                )
                QMessageBox.information(self, "نجاح", "تم تصدير التقرير بنجاح")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء التصدير: {str(e)}")

class AddTransactionDialog(QDialog):
    def __init__(self, deceased_id, db_service, parent=None, forced_currency_code=None, hide_currency_field=False, hide_date_field=False):
        super().__init__(parent)
        self.deceased_id = deceased_id
        self.db_service = db_service
        self.forced_currency_code = forced_currency_code
        self.hide_currency_field = hide_currency_field
        self.hide_date_field = hide_date_field
        self.setWindowTitle("إضافة حركة مالية جديدة")
        self.setMinimumWidth(500)
        
        # 1. ضبط اتجاه النافذة من اليمين إلى اليسار (العربية)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        
        # ضبط محاذاة العناوين لتناسب الاتجاه الأيمن
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # تعريف Locale إنجليزي لفرض الأرقام والتواريخ بالإنجليزية
        self.english_locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)

        # --- 1. الحقول الأساسية ---
        self.combo_type = QComboBox()
        self.combo_type.addItems(["إيداع", "سحب"])
        
        self.combo_currency = QComboBox()
        self.combo_currency.addItems(["ILS", "USD", "JOD", "EUR"])

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 9999999.99)
        self.amount_input.setDecimals(2)
        self.amount_input.setLocale(self.english_locale) # أرقام إنجليزية

        # --- 2. حقل التاريخ المعدل (LineEdit مع Mask) ---
        self.date_input = QLineEdit()
        self.date_input.setLocale(self.english_locale)
        # القناع: 9 تعني رقم إجباري، / ثابتة، _; تعني الفراغ يظهر كـ _
        self.date_input.setInputMask("99/99/9999;_") 
        # وضع تاريخ اليوم كقيمة افتراضية
        self.date_input.setText(QDate.currentDate().toString("dd/MM/yyyy"))

        # --- 3. حقول التوثيق ---
        self.receipt_number = QLineEdit()
        self.receipt_number.setLocale(self.english_locale)
        # self.receipt_number.setPlaceholderText("أرقام فقط")

        self.payer_name = QLineEdit()
        
        self.payment_method = QComboBox()
        self.payment_method.addItems(["اختر", "نقداً", "شيك", "تحويل بنكي"])
        self.payment_method.currentTextChanged.connect(self.toggle_bank_fields)

        # --- 4. حقول البنك (ديناميكية) ---
        self.bank_group_widget = QWidget()
        self.bank_layout = QFormLayout(self.bank_group_widget)
        self.bank_layout.setContentsMargins(0, 0, 0, 0)
        self.bank_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.check_number = QLineEdit()
        self.check_number.setLocale(self.english_locale)
        
        self.bank_name = QLineEdit()
        
        # تاريخ الاستحقاق أيضاً كـ LineEdit بـ Mask
        self.due_date = QLineEdit()
        self.due_date.setLocale(self.english_locale)
        self.due_date.setInputMask("99/99/9999;_")
        # self.due_date.setText(QDate.currentDate().toString("dd/MM/yyyy"))
        
        self.reference_number = QLineEdit()
        self.reference_number.setLocale(self.english_locale)
        
        self.note = QLineEdit()
        
        self.bank_layout.addRow("رقم الشيك:", self.check_number)
        self.bank_layout.addRow("اسم البنك:", self.bank_name)
        self.bank_layout.addRow("تاريخ الاستحقاق:", self.due_date)
        self.bank_layout.addRow("رقم الحوالة:", self.reference_number)

        # إضافة كافة الحقول للنموذج
        self.form_layout.addRow("نوع الحركة:", self.combo_type)
        self.form_layout.addRow("العملة:", self.combo_currency)
        self.form_layout.addRow("المبلغ:", self.amount_input)
        self.form_layout.addRow("رقم سند القبض/الصرف:", self.receipt_number)
        self.form_layout.addRow("المودع/المستفيد:", self.payer_name)
        self.form_layout.addRow("طريقة الإيداع/السحب:", self.payment_method)
        self.form_layout.addRow(self.bank_group_widget)
        self.form_layout.addRow("تاريخ الحركة:", self.date_input)

        self.main_layout.addLayout(self.form_layout)

        if self.forced_currency_code:
            idx = self.combo_currency.findText(self.forced_currency_code)
            if idx >= 0:
                self.combo_currency.setCurrentIndex(idx)

        if self.hide_currency_field:
            currency_label = self.form_layout.labelForField(self.combo_currency)
            if currency_label:
                currency_label.setVisible(False)
            self.combo_currency.setVisible(False)

        if self.hide_date_field:
            date_label = self.form_layout.labelForField(self.date_input)
            if date_label:
                date_label.setVisible(False)
            self.date_input.setVisible(False)

        # --- 5. أزرار التحكم ---
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.buttons.accepted.connect(self.validate_and_save)
        self.buttons.rejected.connect(self.reject)
        self.main_layout.addWidget(self.buttons)

        self.toggle_bank_fields("نقداً")
        
        self.divide_checkbox = QCheckBox("توزيع هذا المبلغ على الأيتام التابعين له")
        self.divide_checkbox.setVisible(True) # يظهر فقط في حالة الإيداع
        # self.combo_type.currentTextChanged.connect(self.toggle_divide_option)
        
        self.division_mode_combo = QComboBox()
        self.division_mode_combo.addItems(["يدوي", "بالتساوي", "للذكر مثل حظ الأنثيين"])
        self.division_mode_combo.setEnabled(False)
        self.divide_checkbox.toggled.connect(self.division_mode_combo.setEnabled)

        self.include_guardian_checkbox = QCheckBox("توزيع المبلغ على الوصي أيضاً")
        self.include_guardian_checkbox.setEnabled(False)
        self.divide_checkbox.toggled.connect(self.include_guardian_checkbox.setEnabled)
        self.divide_checkbox.toggled.connect(
            lambda checked: self.include_guardian_checkbox.setChecked(False) if not checked else None
        )

        self.form_layout.addRow(self.divide_checkbox)
        self.form_layout.addRow("طريقة التقسيم:", self.division_mode_combo)
        self.form_layout.addRow(self.include_guardian_checkbox)
        
        self.form_layout.addRow("ملاحظة:", self.note)

        
        # ربط تغيير النوع (إيداع/سحب) بالدالة الجديدة
        # self.combo_type.currentTextChanged.connect(self.toggle_transaction_type_fields)
        
        # # استدعاء الدالة فوراً لضبط الحالة الابتدائية
        # self.toggle_transaction_type_fields()
    
    def toggle_transaction_type_fields(self):
        """التحكم في ظهور الحقول بناءً على نوع الحركة (إيداع/سحب)"""
        transaction_type = self.combo_type.currentText()
        is_deposit = "إيداع" in transaction_type
        
        # 1. إظهار/إخفاء حقول المودع وطريقة الدفع
        # (ستظهر فقط في حالة الإيداع وتختفي في السحب)
        self.payer_name.setVisible(is_deposit)
        self.form_layout.labelForField(self.payer_name).setVisible(is_deposit)
        
        self.payment_method.setVisible(is_deposit)
        self.form_layout.labelForField(self.payment_method).setVisible(is_deposit)

        # 2. التحكم في حقول البنك (إذا كانت مخفية لأن الحركة سحب)
        if not is_deposit:
            self.bank_group_widget.setVisible(False)
        else:
            # إذا عاد للإيداع، نتحقق من طريقة الدفع المختارة حالياً
            self.toggle_bank_fields(self.payment_method.currentText())

        # 3. إظهار خيار التقسيم (بناءً على طلبك ليكون متاحاً في السحب أيضاً)
        # إذا كنت تريده متاحاً دائماً، نجعله True
        self.divide_checkbox.setVisible(True)
    
    def toggle_divide_option(self, transaction_type):
        """إظهار خيار التقسيم فقط عند الإيداع"""
        is_deposit = "إيداع" in transaction_type
        self.divide_checkbox.setVisible(is_deposit)
        if not is_deposit:
            self.divide_checkbox.setChecked(False)

    def toggle_bank_fields(self, method):
        """ التحكم الديناميكي الكامل في حقول البنك وتاريخ الاستحقاق """
        
        # 1. إظهار الحاوية البنكية فقط إذا لم يكن الدفع نقداً
        is_not_cash = method in ["شيك", "تحويل بنكي"]
        self.bank_group_widget.setVisible(is_not_cash)
        
        if not is_not_cash:
            return

        # 2. جلب العناوين المرتبطة بالحقول للتحكم في ظهورها
        check_label = self.bank_layout.labelForField(self.check_number)
        due_date_label = self.bank_layout.labelForField(self.due_date)
        ref_label = self.bank_layout.labelForField(self.reference_number)

        if method == "شيك":
            # إظهار كل شيء متعلق بالشيك
            check_label.setVisible(True)
            self.check_number.setVisible(True)
            due_date_label.setVisible(True)
            self.due_date.setVisible(True)
            self.reference_number.setVisible(False)
            ref_label.setVisible(False)
            self.reference_number.clear()
            
            # ضبط مسميات الشيك
            due_date_label.setText("تاريخ الاستحقاق:")
            # ref_label.setText("ملاحظات:")
            # self.reference_number.setPlaceholderText("مثلاً: اسم المستفيد")

        elif method == "تحويل بنكي":
            # إخفاء حقل رقم الشيك وتاريخ الاستحقاق تماماً
            check_label.setVisible(False)
            self.check_number.setVisible(False)
            self.check_number.clear()
            self.reference_number.setVisible(True)
            ref_label.setVisible(True)
            
            due_date_label.setVisible(False)
            self.due_date.setVisible(False)
            
            # ضبط مسميات التحويل
            ref_label.setText("رقم الحوالة:")
            self.reference_number.setPlaceholderText("أدخل رقم الحوالة")

    def validate_and_save(self):
        """ التحقق من صحة البيانات قبل الحفظ """
        # 1. التحقق من صلاحية تاريخ الحركة
        q_date = QDate.fromString(self.date_input.text(), "dd/MM/yyyy")
        if not q_date.isValid():
            QMessageBox.warning(self, "خطأ في التاريخ", "يرجى إدخال تاريخ صالح (يوم/شهر/سنة)")
            self.date_input.setFocus()
            return

        # 2. التحقق من الرصيد إذا كانت الحركة سحب
        amount = Decimal(str(self.amount_input.value()))
        currency = self.combo_currency.currentText()
        if "سحب" in self.combo_type.currentText():
            current_bal = self.db_service.get_deceased_balance(self.deceased_id, currency)
            if amount > current_bal:
                QMessageBox.warning(self, "رصيد غير كافٍ", f"الرصيد المتوفر {current_bal} {currency} فقط")
                return

        self.accept()

    def get_transaction_data(self):
        """ استخراج البيانات النهائية لتخزينها في قاعدة البيانات """
        currencies = self.db_service.get_currencies()
        currency_id = None
        selected_code = self.forced_currency_code or self.combo_currency.currentText()
        for c in currencies:
            if c.code == selected_code:
                currency_id = c.id
                break
        
        return {
            "deceased_id": self.deceased_id,
            "currency_id": currency_id,
            "amount": Decimal(str(self.amount_input.value())),
            "type": "deposit" if "إيداع" in self.combo_type.currentText() else "withdraw",
            "receipt_number": self.receipt_number.text().strip(),
            "payer_name": self.payer_name.text().strip(),
            "payment_method": self.payment_method.currentText() if self.payment_method.currentText() != "اختر" else None,
            "check_number": self.check_number.text().strip() if self.check_number.isEnabled() else None,
            "bank_name": self.bank_name.text().strip() or None,
            "due_date": QDate.fromString(self.due_date.text(), "dd/MM/yyyy").toPyDate() if self.bank_group_widget.isVisible() else None,
            "reference_number": self.reference_number.text().strip() or None,
            # "created_at": QDate.fromString(self.date_input.text(), "dd/MM/yyyy").toPyDate()
            "should_distribute": self.divide_checkbox.isChecked(),
            "distribution_mode": self.division_mode_combo.currentText(),
            "include_guardian_share": self.include_guardian_checkbox.isChecked(),
            "note": self.note.text().strip()
        }

class DeceasedSearchDialog(QDialog):
    def __init__(self, db_session, search_term, parent=None):
        super().__init__(parent)
        self.session = db_session
        self.search_term = search_term
        self.selected_deceased = None
        self.init_ui()
        self.perform_search()

    def init_ui(self):
        self.setWindowTitle("نتائج البحث عن المتوفى")
        self.resize(700, 400)
        layout = QVBoxLayout(self)

        # 1. إعداد الجدول
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "اسم المتوفى", "رقم الهوية", "رقم الأرشيف"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        # تحسين حجم الأعمدة
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table)

        # 2. أزرار التحكم
        self.select_btn = QPushButton("اختيار")
        self.select_btn.clicked.connect(self.accept_selection)
        self.select_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; height: 35px;")
        layout.addWidget(self.select_btn)

        # ربط النقر المزدوج بالاختيار المباشر
        self.table.cellDoubleClicked.connect(self.accept_selection)

    def perform_search(self):
        try:
            self.table.setRowCount(0)
            search_query = f"%{self.search_term}%"

            results = self.session.query(Deceased).filter(
                or_(
                    Deceased.name.like(search_query),
                    Deceased.national_id.like(search_query),
                    Deceased.archives_number.like(search_query)
                )
            ).all()
            
            self.table.setRowCount(len(results))
            for row, person in enumerate(results):
                self.table.setItem(row, 0, QTableWidgetItem(str(person.id)))
                self.table.setItem(row, 1, QTableWidgetItem(str(person.name)))
                self.table.setItem(row, 2, QTableWidgetItem(str(person.national_id) if person.national_id else "---"))
                self.table.setItem(row, 3, QTableWidgetItem(str(person.archives_number) if person.archives_number else "---"))
                
                # تخزين الكائن للوصول إليه عند الاختيار
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, person)

        except Exception as e:
            print(f"Error in DB Query: {e}")
    
    def accept_selection(self):
        """تأكيد الاختيار وإغلاق النافذة"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            # استعادة كائن الشخص من الـ UserRole
            self.selected_deceased = self.table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            self.accept()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار سجل من الجدول أولاً.")

    def get_selected_deceased(self):
        """دالة عامة للحصول على الشخص المختار بعد إغلاق النافذة"""
        return self.selected_deceased

class AddTTableRowDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.english_locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        self.enable_distribution_trace = True
        self.entity_amount_inputs = {}
        self.entity_type_inputs = {}
        self.entity_balances = {}
        self.entity_meta = {}
        self.entity_extra_details = {}
        self.entity_details_buttons = {}
        self.deceased_available_balance = Decimal("0")
        self.setWindowTitle("حركة مالية جديدة")
        self.setMinimumSize(680, 500)
        self.resize(700, 560)
        self.init_ui()

    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(8)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(8)

        self.scroll_area.setWidget(self.scroll_content)
        outer_layout.addWidget(self.scroll_area)

        self.top_grid = QGridLayout()
        self.top_grid.setHorizontalSpacing(12)
        self.top_grid.setVerticalSpacing(8)
        self.main_layout.addLayout(self.top_grid)

        self.transaction_date = QLineEdit()
        self.transaction_date.setPlaceholderText("تاريخ المعاملة")
        self.transaction_date.setInputMask("99/99/9999;_") # تنسيق يوم/شهر/سنة
        self.transaction_date.setText(QDate.currentDate().toString("dd/MM/yyyy"))
        
        self.transaction_type = QComboBox()
        self.transaction_type.addItems(["اختر", "إيداع", "سحب"])

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.00, 9999999.99)
        self.amount_input.setDecimals(2)
        self.amount_input.setLocale(self.english_locale)
        self.amount_input.setSingleStep(10.00)

        self.deceased_balance_label = QLabel("رصيد المتوفي المتاح: 0.00")
        self.deceased_balance_label.setStyleSheet("color: #1f2937; font-weight: bold;")
        
        self.receipt_number_input = QLineEdit()
        self.receipt_number_input.setPlaceholderText("رقم سند القبض/الصرف")
        
        self.depositor_input = QLineEdit()
        self.depositor_input.setPlaceholderText("المودع / المستفيد")
        
        self.payment_method_input = QComboBox()
        self.payment_method_input.addItems(["اختر", "نقداً", "شيك", "تحويل بنكي"])
        
        self.payment_method_input.currentTextChanged.connect(self.toggle_payment_fields)
        self.transaction_type.currentTextChanged.connect(self.on_transaction_type_changed)
        
        self.check_number_input = QLineEdit()
        self.check_number_input.setPlaceholderText("رقم الشيك")

        self.bank_name_input = QLineEdit()
        self.bank_name_input.setPlaceholderText("اسم البنك")

        self.due_date_input = QLineEdit()
        self.due_date_input.setPlaceholderText("تاريخ الاستحقاق")
        self.due_date_input.setInputMask("99/99/9999;_") # تنسيق يوم/شهر/سنة

        self.reference_number_input = QLineEdit()
        self.reference_number_input.setPlaceholderText("رقم الحوالة")

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("ملاحظة")

        self._add_pair_row(0, ("تاريخ الحركة", self.transaction_date), ("نوع الحركة", self.transaction_type))
        self._add_pair_row(1, ("المبلغ", self.amount_input), ("طريقة الإيداع/السحب", self.payment_method_input))
        self._add_pair_row(2, ("رقم سند القبض/الصرف", self.receipt_number_input), ("المودع/المستفيد", self.depositor_input))

        self.check_due_row = self._add_pair_row(3, ("رقم الشيك", self.check_number_input), ("تاريخ الاستحقاق", self.due_date_input))
        self.bank_ref_row = self._add_pair_row(4, ("اسم البنك", self.bank_name_input), ("رقم الحوالة", self.reference_number_input))
        self.note_row = self._create_labeled_field("ملاحظة", self.note_input)

        self.main_layout.addWidget(self.deceased_balance_label)

        self.divide_checkbox = QCheckBox("تفعيل التوزيع من مبلغ المتوفي")
        self.main_layout.addWidget(self.divide_checkbox)

        self.distribution_targets_row = QWidget()
        targets_layout = QHBoxLayout(self.distribution_targets_row)
        targets_layout.setContentsMargins(0, 0, 0, 0)
        targets_layout.setSpacing(12)
        self.distribute_to_guardian_checkbox = QCheckBox("توزيع على الوصي")
        self.distribute_to_guardian_checkbox.setChecked(False)
        targets_layout.addWidget(self.distribute_to_guardian_checkbox)
        targets_layout.addStretch()

        self.division_mode_row = QWidget()
        dist_layout = QHBoxLayout(self.division_mode_row)
        dist_layout.setContentsMargins(0, 0, 0, 0)
        dist_layout.setSpacing(8)
        dist_layout.addWidget(QLabel("نوع التقسيم:"))
        self.division_mode_combo = QComboBox()
        self.division_mode_combo.addItems(["يدوي", "بالتساوي", "للذكر مثل حظ الأنثيين"])
        self.division_mode_combo.setEnabled(False)
        dist_layout.addWidget(self.division_mode_combo)
        dist_layout.addStretch()
        self.main_layout.addWidget(self.division_mode_row)
        self.main_layout.addWidget(self.distribution_targets_row)

        self.distribution_hint = QLabel("")
        self.distribution_hint.setStyleSheet("color: #6b7280;")
        self.main_layout.addWidget(self.distribution_hint)

        self.dynamic_section_title = QLabel("جدول الأيتام/الوصي")
        self.dynamic_section_title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.main_layout.addWidget(self.dynamic_section_title)

        self.entities_table = QTableWidget()
        self.entities_table.setColumnCount(6)
        self.entities_table.setHorizontalHeaderLabels(["الاسم", "الصفة", "الرصيد الحالي", "نوع الحركة", "مبلغ العملية", "تفاصيل"])
        self.entities_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.entities_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.entities_table.verticalHeader().setVisible(False)
        self.entities_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.entities_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.entities_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.entities_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.entities_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.entities_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.entities_table.setMinimumHeight(250)
        self.entities_table.setMaximumHeight(340)
        self.main_layout.addWidget(self.entities_table)
        self.main_layout.addWidget(self.note_row)

        self.build_dynamic_entity_fields()

        self.divide_checkbox.toggled.connect(self.on_distribution_settings_changed)
        self.distribute_to_guardian_checkbox.toggled.connect(self.on_distribution_settings_changed)
        self.division_mode_combo.currentTextChanged.connect(self.on_distribution_settings_changed)
        self.amount_input.valueChanged.connect(self.on_distribution_settings_changed)
        

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

        # Apply initial visibility state for payment-related fields.
        self.toggle_payment_fields(self.payment_method_input.currentText())
        self.on_transaction_type_changed(self.transaction_type.currentText())
        self.on_distribution_settings_changed()

    def _create_labeled_field(self, label_text, field_widget):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        label = QLabel(f"{label_text}:")
        label.setStyleSheet("font-weight: 600;")
        layout.addWidget(label)
        layout.addWidget(field_widget)
        field_widget._pair_wrapper = wrapper
        return wrapper

    def _add_pair_row(self, row_index, left_item, right_item):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        if left_item:
            row_layout.addWidget(self._create_labeled_field(left_item[0], left_item[1]), 1)
        if right_item:
            row_layout.addWidget(self._create_labeled_field(right_item[0], right_item[1]), 1)
        else:
            row_layout.addStretch(1)

        self.top_grid.addWidget(row_widget, row_index, 0)
        return row_widget

    def _add_full_width_row(self, row_index, label_text, field_widget):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.addWidget(self._create_labeled_field(label_text, field_widget), 1)

        self.top_grid.addWidget(row_widget, row_index, 0)
        return row_widget

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _collect_entities_from_parent(self):
        parent = self.parent()
        entities = []
        if not parent:
            return entities

        raw_entities = getattr(parent, "t_table_entities", []) or []
        for idx, entity in enumerate(raw_entities):
            kind = (entity.get("kind") or "").strip()
            entity_id = entity.get("id")
            name = (entity.get("name") or "").strip()
            if not kind or entity_id is None or not name:
                continue

            balance = 0.0
            table = getattr(parent, "t_table", None)
            if table is not None:
                dep_col = 3 + (idx * 2)
                wd_col = dep_col + 1
                if wd_col < table.columnCount():
                    for row in range(2, table.rowCount()):
                        dep_item = table.item(row, dep_col)
                        wd_item = table.item(row, wd_col)
                        dep_val = 0.0
                        wd_val = 0.0
                        if dep_item and dep_item.text().strip():
                            try:
                                dep_val = float(dep_item.text().strip().replace(',', ''))
                            except ValueError:
                                dep_val = 0.0
                        if wd_item and wd_item.text().strip():
                            try:
                                wd_val = float(wd_item.text().strip().replace(',', ''))
                            except ValueError:
                                wd_val = 0.0
                        balance += dep_val - wd_val

            entities.append({
                "kind": kind,
                "id": entity_id,
                "name": name,
                "balance": balance,
                "gender": self._get_entity_gender_from_parent(kind, entity_id),
            })

        return entities

    def _get_entity_gender_from_parent(self, kind, entity_id):
        if kind != "orphan":
            return None
        parent = self.parent()
        if not parent:
            return None
        for orphan in getattr(parent, "d_orphans", []) or []:
            if getattr(orphan, "id", None) == entity_id:
                return getattr(orphan, "gender", None)

        # Fallback: read gender from DB if orphan is not present in parent's in-memory list.
        db_service = getattr(parent, "db_service", None)
        session = getattr(db_service, "session", None) if db_service else None
        if session is not None:
            try:
                orphan = session.query(Orphan).filter_by(id=entity_id).first()
                if orphan is not None:
                    return getattr(orphan, "gender", None)
            except Exception:
                pass
        return None

    def _is_gender_mode(self, mode_text):
        normalized = str(mode_text or "").strip().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
        return "للذكر" in normalized and "حظ" in normalized

    def _calculate_deceased_available_balance_from_parent(self):
        parent = self.parent()
        if not parent:
            return Decimal("0")

        deceased = getattr(parent, "current_deceased_for_t_table", None)
        db_service = getattr(parent, "db_service", None)
        c_combo = getattr(parent, "c_combo", None)
        if not deceased or not db_service or not c_combo:
            return Decimal("0")

        currency_code = (c_combo.currentText() or "").strip()
        if not currency_code:
            return Decimal("0")

        try:
            return Decimal(str(db_service.get_deceased_balance(deceased.id, currency_code) or 0))
        except Exception:
            return Decimal("0")

    def build_dynamic_entity_fields(self):
        self.entities_table.setRowCount(0)
        self.entity_amount_inputs.clear()
        self.entity_type_inputs.clear()
        self.entity_balances.clear()
        self.entity_meta.clear()
        self.entity_extra_details.clear()
        self.entity_details_buttons.clear()

        self.deceased_available_balance = self._calculate_deceased_available_balance_from_parent()
        self.deceased_balance_label.setText(f"رصيد المتوفي المتاح: {self.deceased_available_balance:,.2f}")

        entities = self._collect_entities_from_parent()
        if not entities:
            self.entities_table.setRowCount(1)
            self.entities_table.setSpan(0, 0, 1, 6)
            hint_item = QTableWidgetItem("لا توجد بيانات أيتام/وصي حالياً. اختر متوفى أولاً ثم أعد فتح النافذة.")
            hint_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.entities_table.setItem(0, 0, hint_item)
            return

        self.entities_table.setRowCount(len(entities))
        for row, entity in enumerate(entities):
            role_text = "يتيم" if entity["kind"] == "orphan" else "وصي"

            name_item = QTableWidgetItem(entity["name"])
            role_item = QTableWidgetItem(role_text)
            balance_item = QTableWidgetItem(f"{entity['balance']:,.2f}")

            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            role_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.entities_table.setItem(row, 0, name_item)
            self.entities_table.setItem(row, 1, role_item)
            self.entities_table.setItem(row, 2, balance_item)

            type_combo = QComboBox()
            type_combo.addItems(["إيداع", "سحب"])
            type_combo.setCurrentText(self.transaction_type.currentText())
            type_combo.currentTextChanged.connect(self._refresh_distribution_hint_text)
            self.entities_table.setCellWidget(row, 3, type_combo)

            amount_input = QDoubleSpinBox()
            amount_input.setRange(0.00, 9999999.99)
            amount_input.setDecimals(2)
            amount_input.setSingleStep(10.00)
            amount_input.setLocale(self.english_locale)
            amount_input.setMinimumWidth(150)
            amount_input.valueChanged.connect(self._refresh_distribution_hint_text)
            self.entities_table.setCellWidget(row, 4, amount_input)

            key = (entity["kind"], entity["id"])
            self.entity_type_inputs[key] = type_combo
            self.entity_amount_inputs[key] = amount_input
            self.entity_balances[key] = float(entity["balance"])
            self.entity_meta[key] = entity

            details_btn = QPushButton("تفاصيل")
            details_btn.setMinimumWidth(95)
            details_btn.clicked.connect(lambda _, local_key=key: self._open_entity_details_dialog(local_key))
            self.entities_table.setCellWidget(row, 5, details_btn)
            self.entity_details_buttons[key] = details_btn

        self.entities_table.resizeRowsToContents()

    def _normalize_optional_text(self, value):
        text = str(value or "").strip()
        return text if text else None

    def _sanitize_entity_details(self, details):
        if not isinstance(details, dict):
            details = {}

        return {
            "document_number": self._normalize_optional_text(details.get("document_number")),
            "person_name": self._normalize_optional_text(details.get("person_name")),
            "payment_method": self._normalize_optional_text(details.get("payment_method")),
            "check_number": self._normalize_optional_text(details.get("check_number")),
            "due_date": self._normalize_optional_text(details.get("due_date")),
            "bank_name": self._normalize_optional_text(details.get("bank_name")),
            "reference_number": self._normalize_optional_text(details.get("reference_number")),
        }

    def _build_default_entity_details(self, key):
        meta = self.entity_meta.get(key, {})
        defaults = {
            "document_number": "",
            "person_name": meta.get("name") or "",
            "payment_method": "",
            "check_number": "",
            "due_date": "",
            "bank_name": "",
            "reference_number": "",
        }

        existing = self.entity_extra_details.get(key) or {}
        for field_name in defaults.keys():
            existing_value = existing.get(field_name)
            if existing_value:
                defaults[field_name] = str(existing_value)

        return defaults

    def _open_entity_details_dialog(self, key):
        dialog = QDialog(self)
        dialog.setWindowTitle("تفاصيل إضافية للحركة")
        dialog.setMinimumWidth(430)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        defaults = self._build_default_entity_details(key)

        document_number_input = QLineEdit(defaults["document_number"])
        person_name_input = QLineEdit(defaults["person_name"])

        payment_method_combo = QComboBox()
        payment_method_combo.addItems(["اختر", "نقداً", "شيك", "تحويل بنكي"])
        pm_idx = payment_method_combo.findText(defaults["payment_method"])
        if pm_idx >= 0:
            payment_method_combo.setCurrentIndex(pm_idx)

        check_number_input = QLineEdit(defaults["check_number"])
        due_date_input = QLineEdit(defaults["due_date"])
        due_date_input.setInputMask("99/99/9999;_")
        bank_name_input = QLineEdit(defaults["bank_name"])
        reference_number_input = QLineEdit(defaults["reference_number"])

        form.addRow("طريقة الدفع/السحب:", payment_method_combo)
        form.addRow("رقم سند القبض/الصرف:", document_number_input)
        form.addRow("المودع/المستفيد:", person_name_input)
        form.addRow("رقم الشيك:", check_number_input)
        form.addRow("تاريخ الاستحقاق:", due_date_input)
        form.addRow("اسم البنك:", bank_name_input)
        form.addRow("رقم المرجع/الحوالة:", reference_number_input)
        layout.addLayout(form)

        check_label = form.labelForField(check_number_input)
        due_label = form.labelForField(due_date_input)
        bank_label = form.labelForField(bank_name_input)
        reference_label = form.labelForField(reference_number_input)
        document_label = form.labelForField(document_number_input)
        person_label = form.labelForField(person_name_input)

        def set_pair_visibility(label_widget, field_widget, visible):
            if label_widget is not None:
                label_widget.setVisible(visible)
            field_widget.setVisible(visible)

        def sync_fields_by_payment_method(method_text):
            method_text = str(method_text or "").strip()
            is_selected = method_text != "اختر"
            is_check = method_text == "شيك"
            is_transfer = method_text == "تحويل بنكي"

            # نقداً: لا نعرض حقول الشيك/الاستحقاق/البنك/المرجع.
            # شيك: نعرض الشيك + الاستحقاق + البنك.
            # تحويل بنكي: نعرض البنك + المرجع.
            # بدون اختيار: لا نعرض أي حقل تفصيلي.
            set_pair_visibility(document_label, document_number_input, is_selected)
            set_pair_visibility(person_label, person_name_input, is_selected)
            set_pair_visibility(check_label, check_number_input, is_selected and is_check)
            set_pair_visibility(due_label, due_date_input, is_selected and is_check)
            set_pair_visibility(bank_label, bank_name_input, is_selected and (is_check or is_transfer))
            set_pair_visibility(reference_label, reference_number_input, is_selected and is_transfer)

            if not is_selected:
                document_number_input.clear()
                person_name_input.clear()

            if not (is_selected and is_check):
                check_number_input.clear()
                due_date_input.clear()
            if not (is_selected and (is_check or is_transfer)):
                bank_name_input.clear()
            if not (is_selected and is_transfer):
                reference_number_input.clear()

        payment_method_combo.currentTextChanged.connect(sync_fields_by_payment_method)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        def on_save_clicked():
            due_text = due_date_input.text().strip()
            due_digits_only = due_text.replace("/", "").replace("_", "").strip()
            normalized_due_text = due_text if due_digits_only else ""

            if normalized_due_text:
                q_date = QDate.fromString(due_text, "dd/MM/yyyy")
                if not q_date.isValid():
                    QMessageBox.warning(dialog, "تنبيه", "تاريخ الاستحقاق غير صالح. استخدم تنسيق يوم/شهر/سنة.")
                    due_date_input.setFocus()
                    return

            self.entity_extra_details[key] = self._sanitize_entity_details({
                "document_number": document_number_input.text(),
                "person_name": person_name_input.text(),
                "payment_method": payment_method_combo.currentText(),
                "check_number": check_number_input.text(),
                "due_date": normalized_due_text,
                "bank_name": bank_name_input.text(),
                "reference_number": reference_number_input.text(),
            })

            button_row = self._find_entity_row_by_key(key)
            if button_row >= 0:
                row_button = self.entities_table.cellWidget(button_row, 5)
                if isinstance(row_button, QPushButton):
                    row_button.setText("تعديل التفاصيل")

            dialog.accept()

        buttons.accepted.connect(on_save_clicked)
        buttons.rejected.connect(dialog.reject)

        sync_fields_by_payment_method(payment_method_combo.currentText())
        dialog.exec()

    def _find_entity_row_by_key(self, key):
        target_meta = self.entity_meta.get(key)
        if not target_meta:
            return -1

        target_name = str(target_meta.get("name") or "").strip()
        target_kind = str(target_meta.get("kind") or "").strip()
        for row in range(self.entities_table.rowCount()):
            name_item = self.entities_table.item(row, 0)
            role_item = self.entities_table.item(row, 1)
            if not name_item or not role_item:
                continue

            row_name = name_item.text().strip()
            row_role = role_item.text().strip()
            row_kind = "orphan" if row_role == "يتيم" else "guardian"
            if row_name == target_name and row_kind == target_kind:
                return row
        return -1

    def on_transaction_type_changed(self, text):
        is_deposit = "إيداع" in text
        is_type_selected = text in ["إيداع", "سحب"]

        self._update_transaction_type_dependent_visibility(is_type_selected)
        is_distributing = self.divide_checkbox.isChecked()

        for key, input_widget in self.entity_amount_inputs.items():
            input_widget.setPrefix("")
            input_widget.setSuffix("")
            type_combo = self.entity_type_inputs.get(key)
            if type_combo and is_type_selected and is_distributing:
                type_combo.setCurrentText("إيداع")
        self.on_distribution_settings_changed()

    def _update_transaction_type_dependent_visibility(self, is_type_selected: bool):
        amount_wrapper = getattr(self.amount_input, "_pair_wrapper", self.amount_input)
        payment_wrapper = getattr(self.payment_method_input, "_pair_wrapper", self.payment_method_input)

        amount_wrapper.setVisible(is_type_selected)
        payment_wrapper.setVisible(is_type_selected)
        self.deceased_balance_label.setVisible(is_type_selected)
        self.divide_checkbox.setVisible(is_type_selected)
        self.distribution_targets_row.setVisible(is_type_selected)
        self.division_mode_row.setVisible(is_type_selected)
        self.distribution_hint.setVisible(is_type_selected)

        if not is_type_selected:
            self.amount_input.setValue(0.0)
            self.payment_method_input.setCurrentText("اختر")
            self.divide_checkbox.setChecked(False)
            self.division_mode_combo.setCurrentIndex(0)
            self.distribute_to_guardian_checkbox.setChecked(False)
            for key, input_widget in self.entity_amount_inputs.items():
                input_widget.blockSignals(True)
                input_widget.setValue(0.0)
                input_widget.blockSignals(False)
                type_combo = self.entity_type_inputs.get(key)
                if type_combo:
                    type_combo.setCurrentText("إيداع")

    def _refresh_distribution_hint_text(self):
        if self.divide_checkbox.isChecked() and self.division_mode_combo.currentText() == "يدوي":
            entered = self._sum_entity_amounts(selected_only=True)
            base_amount = Decimal(str(self.amount_input.value()))
            if "سحب" in self.transaction_type.currentText():
                self.distribution_hint.setText(
                    f"التوزيع اليدوي الحالي: {entered:,.2f} | يجب أن يساوي مبلغ السحب: {base_amount:,.2f}"
                )
            else:
                self.distribution_hint.setText(
                    f"التوزيع اليدوي الحالي: {entered:,.2f} | الحد الأعلى: {base_amount:,.2f}"
                )
        else:
            self.distribution_hint.setText("")

    def _sum_entity_amounts(self, selected_only=False):
        total = Decimal("0")
        for key, input_widget in self.entity_amount_inputs.items():
            if selected_only and not self._is_entity_selected_for_distribution(key):
                continue
            total += Decimal(str(input_widget.value()))
        return total

    def _is_entity_selected_for_distribution(self, key):
        kind = key[0]
        if kind == "orphan":
            return True
        if kind == "guardian":
            return self.distribute_to_guardian_checkbox.isChecked()
        return True

    def _get_distribution_keys(self):
        return [key for key in self.entity_amount_inputs.keys() if self._is_entity_selected_for_distribution(key)]

    def _distribute_equally(self, amount: Decimal, keys):
        shares = {key: Decimal("0.00") for key in keys}
        if amount <= 0 or not keys:
            return shares

        n = Decimal(len(keys))
        base = (amount / n).quantize(Decimal("0.01"))
        assigned = Decimal("0.00")
        for i, key in enumerate(keys):
            if i < len(keys) - 1:
                shares[key] = base
                assigned += base
            else:
                shares[key] = (amount - assigned).quantize(Decimal("0.01"))
        return shares

    def _gender_weight(self, gender_value):
        if gender_value is None:
            return Decimal("1")

        # Handle enum-like values (e.g., GenderEnum.male with value 1).
        enum_name = getattr(gender_value, "name", None)
        enum_value = getattr(gender_value, "value", None)
        if isinstance(enum_name, str) and enum_name.lower() == "male":
            return Decimal("2")
        if enum_value == 1:
            return Decimal("2")

        # Handle int/string representations.
        if isinstance(gender_value, int):
            return Decimal("2") if gender_value == 1 else Decimal("1")

        gender_text = str(gender_value or "").strip().lower().replace("genderenum.", "")
        male_tokens = {"male", "m", "ذكر", "1"}
        female_tokens = {"female", "f", "انثى", "أنثى", "2"}

        if gender_text in male_tokens:
            return Decimal("2")
        if gender_text in female_tokens:
            return Decimal("1")

        # Default to female share when value is unknown to avoid over-distribution.
        return Decimal("1")

    def _distribute_by_gender(self, amount: Decimal, keys):
        shares = {key: Decimal("0.00") for key in keys}
        if amount <= 0 or not keys:
            return shares

        weights = []
        total_weight = Decimal("0")
        for key in keys:
            meta = self.entity_meta.get(key, {})
            if meta.get("kind") == "orphan":
                weight = self._gender_weight(meta.get("gender"))
            else:
                weight = Decimal("1")
            weights.append(weight)
            total_weight += weight

        if total_weight <= 0:
            return self._distribute_equally(amount, keys)

        assigned = Decimal("0.00")
        for i, key in enumerate(keys):
            if i < len(keys) - 1:
                share = (amount * (weights[i] / total_weight)).quantize(Decimal("0.01"))
                shares[key] = share
                assigned += share
            else:
                shares[key] = (amount - assigned).quantize(Decimal("0.01"))
        return shares

    def _apply_auto_distribution(self):
        amount = Decimal(str(self.amount_input.value()))
        keys = self._get_distribution_keys()
        mode = self.division_mode_combo.currentText()

        if self._is_gender_mode(mode):
            shares = self._distribute_by_gender(amount, keys)
        else:
            shares = self._distribute_equally(amount, keys)

        if self.enable_distribution_trace and self._is_gender_mode(mode):
            self._trace_gender_distribution(amount, keys, shares)

        for key, input_widget in self.entity_amount_inputs.items():
            input_widget.blockSignals(True)
            input_widget.setValue(float(shares.get(key, Decimal("0.00"))))
            input_widget.blockSignals(False)

    def _trace_gender_distribution(self, amount: Decimal, keys, shares):
        try:
            print("\n[TTableDistTrace] mode=للذكر مثل حظ الأنثيين")
            print(f"[TTableDistTrace] amount={amount} keys={len(keys)}")

            total_weight = Decimal("0")
            rows = []
            for key in keys:
                meta = self.entity_meta.get(key, {})
                kind = meta.get("kind")
                name = meta.get("name")
                gender = meta.get("gender")
                if kind == "orphan":
                    weight = self._gender_weight(gender)
                else:
                    weight = Decimal("1")
                total_weight += weight
                rows.append((key, kind, name, gender, weight, shares.get(key, Decimal("0.00"))))

            print(f"[TTableDistTrace] total_weight={total_weight}")
            for key, kind, name, gender, weight, share in rows:
                print(
                    f"[TTableDistTrace] key={key} kind={kind} name={name} "
                    f"gender={gender} weight={weight} share={share}"
                )
        except Exception as trace_error:
            print(f"[TTableDistTrace] trace-error: {trace_error}")

    def on_distribution_settings_changed(self):
        distributing = self.divide_checkbox.isChecked()
        mode = self.division_mode_combo.currentText()
        is_manual = mode == "يدوي"

        self.division_mode_combo.setEnabled(distributing)
        self.distribute_to_guardian_checkbox.setEnabled(distributing)

        for key, input_widget in self.entity_amount_inputs.items():
            can_edit_manual = is_manual and self._is_entity_selected_for_distribution(key)
            input_widget.setEnabled((not distributing) or can_edit_manual)
            type_combo = self.entity_type_inputs.get(key)
            if type_combo:
                if distributing:
                    type_combo.setCurrentText("إيداع")
                    type_combo.setEnabled(False)
                else:
                    type_combo.setEnabled(True)

            if distributing and not self._is_entity_selected_for_distribution(key):
                input_widget.blockSignals(True)
                input_widget.setValue(0.0)
                input_widget.blockSignals(False)

            details_btn = self.entity_details_buttons.get(key)
            if details_btn:
                details_btn.setEnabled(not distributing)

        if distributing and not is_manual:
            self._apply_auto_distribution()

        self._refresh_distribution_hint_text()

    def toggle_payment_fields(self, method):
        is_selected = method != "اختر"
        is_check = method == "شيك"
        is_transfer = method == "تحويل بنكي"
        self.check_due_row.setVisible(is_check)
        self.bank_ref_row.setVisible(is_check or is_transfer)

        receipt_wrapper = getattr(self.receipt_number_input, "_pair_wrapper", self.receipt_number_input)
        depositor_wrapper = getattr(self.depositor_input, "_pair_wrapper", self.depositor_input)
        check_wrapper = getattr(self.check_number_input, "_pair_wrapper", self.check_number_input)
        due_wrapper = getattr(self.due_date_input, "_pair_wrapper", self.due_date_input)
        bank_wrapper = getattr(self.bank_name_input, "_pair_wrapper", self.bank_name_input)
        ref_wrapper = getattr(self.reference_number_input, "_pair_wrapper", self.reference_number_input)

        receipt_wrapper.setVisible(is_selected)
        depositor_wrapper.setVisible(is_selected)
        check_wrapper.setVisible(is_check)
        due_wrapper.setVisible(is_check)
        bank_wrapper.setVisible(is_check or is_transfer)
        ref_wrapper.setVisible(is_transfer)

        # إعادة القيم الافتراضية للحقول المخفية
        if not is_selected:
            self.receipt_number_input.clear()
            self.depositor_input.clear()
            self.check_number_input.clear()
            self.bank_name_input.clear()
            self.due_date_input.clear()
            self.reference_number_input.clear()
        elif method == "شيك":
            self.reference_number_input.clear()
        elif method == "تحويل بنكي":
            self.check_number_input.clear()
            self.due_date_input.clear()
        else:  # نقداً
            self.check_number_input.clear()
            self.bank_name_input.clear()
            self.due_date_input.clear()
            self.reference_number_input.clear()

    def validate_and_accept(self):
        q_date = QDate.fromString(self.transaction_date.text(), "dd/MM/yyyy")
        if not q_date.isValid():
            QMessageBox.warning(self, "خطأ", "يرجى إدخال تاريخ صحيح (يوم/شهر/سنة).")
            self.transaction_date.setFocus()
            return

        tx_type = self.transaction_type.currentText()
        has_deceased_type = tx_type in ["إيداع", "سحب"]
        is_withdraw = tx_type == "سحب"
        is_distributing = self.divide_checkbox.isChecked()
        is_manual_distribution = is_distributing and self.division_mode_combo.currentText() == "يدوي"
        deceased_amount = Decimal(str(self.amount_input.value()))
        entities_sum = self._sum_entity_amounts(selected_only=is_distributing)

        # نوع الحركة للمتوفي اختياري، ولكن عند اختياره تصبح حقوله الأساسية إلزامية.
        if has_deceased_type and deceased_amount <= 0:
            QMessageBox.warning(self, "تنبيه", "عند اختيار نوع الحركة للمتوفي يجب إدخال مبلغ أكبر من صفر.")
            self.amount_input.setFocus()
            return

        has_any_entity_amount = False
        for key, input_widget in self.entity_amount_inputs.items():
            if is_distributing and not self._is_entity_selected_for_distribution(key):
                continue
            amount = Decimal(str(input_widget.value()))
            if amount <= 0:
                continue
            has_any_entity_amount = True
            entity_type_combo = self.entity_type_inputs.get(key)
            entity_is_withdraw = bool(entity_type_combo and "سحب" in entity_type_combo.currentText())
            if entity_is_withdraw and not is_distributing:
                available = Decimal(str(self.entity_balances.get(key, 0.0)))
                if amount > available:
                    QMessageBox.warning(
                        self,
                        "رصيد غير كافٍ",
                        "مبلغ السحب لأحد الأيتام/الوصي أكبر من رصيده المتاح."
                    )
                    input_widget.setFocus()
                    return

        if is_withdraw and has_deceased_type and deceased_amount > self.deceased_available_balance:
            QMessageBox.warning(
                self,
                "رصيد المتوفي غير كافٍ",
                f"رصيد المتوفي المتاح {self.deceased_available_balance:,.2f} فقط."
            )
            self.amount_input.setFocus()
            return

        if is_distributing and (not has_deceased_type or deceased_amount <= 0):
            QMessageBox.warning(self, "تنبيه", "أدخل مبلغ حركة المتوفي أولاً قبل التوزيع.")
            self.amount_input.setFocus()
            return

        if is_manual_distribution:
            if entities_sum <= 0:
                QMessageBox.warning(self, "تنبيه", "في التوزيع اليدوي يجب إدخال مبالغ للأيتام/الوصي.")
                return

            if is_withdraw:
                if entities_sum != deceased_amount:
                    QMessageBox.warning(
                        self,
                        "تنبيه",
                        "في سحب + توزيع يدوي يجب أن يساوي مجموع التوزيع مبلغ السحب بالكامل."
                    )
                    return
            else:
                if entities_sum > deceased_amount:
                    QMessageBox.warning(
                        self,
                        "تنبيه",
                        "مجموع التوزيع اليدوي لا يجوز أن يتجاوز مبلغ إيداع المتوفي."
                    )
                    return

        if not is_distributing and deceased_amount <= 0 and not has_any_entity_amount:
            QMessageBox.warning(self, "تنبيه", "أدخل مبلغاً للمتوفي أو لأحد الأيتام/الوصي على الأقل.")
            return

        self.accept()

    def get_data(self):
        tx_type = self.transaction_type.currentText()
        has_deceased_type = tx_type in ["إيداع", "سحب"]
        is_deposit = tx_type == "إيداع"
        is_distributing = self.divide_checkbox.isChecked()
        is_manual_distribution = is_distributing and self.division_mode_combo.currentText() == "يدوي"
        include_orphans_share = is_distributing
        include_guardian_share = self.distribute_to_guardian_checkbox.isChecked()
        beneficiary_transactions = []
        orphan_transactions = []
        guardian_transactions = []
        distributed_total = Decimal("0")

        for (kind, person_id), input_widget in self.entity_amount_inputs.items():
            if is_distributing and not self._is_entity_selected_for_distribution((kind, person_id)):
                continue

            amount = Decimal(str(input_widget.value()))
            if amount <= 0:
                # تفاصيل بدون مبلغ لا يجب أن تنتج حركة للأيتام/الوصي.
                self.entity_extra_details.pop((kind, person_id), None)
                continue

            entity_type_combo = self.entity_type_inputs.get((kind, person_id))
            if is_distributing:
                entity_is_deposit = True
            else:
                entity_is_deposit = bool(entity_type_combo and "إيداع" in entity_type_combo.currentText())

            if is_distributing:
                deposit_amount = amount if entity_is_deposit else Decimal("0")
                withdraw_amount = amount if not entity_is_deposit else Decimal("0")
            else:
                deposit_amount = amount if entity_is_deposit else Decimal("0")
                withdraw_amount = amount if not entity_is_deposit else Decimal("0")

            entry = {
                "kind": kind,
                "person_id": person_id,
                "deposit": deposit_amount,
                "withdraw": withdraw_amount,
            }
            beneficiary_transactions.append(entry)
            distributed_total += deposit_amount

            if kind == "orphan":
                orphan_transactions.append({
                    "orphan_id": person_id,
                    "deposit": entry["deposit"],
                    "withdraw": entry["withdraw"],
                    **self._sanitize_entity_details(self.entity_extra_details.get((kind, person_id))),
                })
            elif kind == "guardian":
                guardian_transactions.append({
                    "guardian_id": person_id,
                    "deposit": entry["deposit"],
                    "withdraw": entry["withdraw"],
                    **self._sanitize_entity_details(self.entity_extra_details.get((kind, person_id))),
                })

        deceased_amount = Decimal(str(self.amount_input.value()))

        return {
            "date_text": self.transaction_date.text().strip(),
            "type": "deposit" if is_deposit else ("withdraw" if has_deceased_type else None),
            "amount": deceased_amount,
            "receipt_number": self.receipt_number_input.text().strip(),
            "payer_name": self.depositor_input.text().strip(),
            "payment_method": self.payment_method_input.currentText() if self.payment_method_input.currentText() != "اختر" else None,
            "check_number": self.check_number_input.text().strip(),
            "bank_name": self.bank_name_input.text().strip(),
            "due_date": self.due_date_input.text().strip(),
            "reference_number": self.reference_number_input.text().strip(),
            "note": self.note_input.text().strip(),
            "should_distribute": is_distributing,
            "include_orphans_share": include_orphans_share,
            "include_guardian_share": include_guardian_share,
            "distribution_mode": self.division_mode_combo.currentText(),
            "distributed_total": distributed_total,
            "deceased_only_transaction": has_deceased_type and deceased_amount > 0 and not is_distributing,
            "has_independent_beneficiary_transactions": len(beneficiary_transactions) > 0 and not is_distributing,
            "beneficiary_transactions": beneficiary_transactions,
            "orphans_transactions": orphan_transactions,
            "guardian_transactions": guardian_transactions,
        }