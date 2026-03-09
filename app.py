import math
import os
import sys
import warnings
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.uic import loadUiType
from datetime import datetime, date
from uuid import uuid4
from decimal import Decimal
import bcrypt
import logging

from sqlalchemy import or_, and_, func
from components.dialogs import AddTTableRowDialog
from database.backup import BackupManager
from database.models import (
    ActivityLog, DeceasedBalance, DeceasedTransaction, Orphan, Guardian, Deceased, Currency,
    Permission, Role, RolePermission, TransactionTypeEnum,
    OrphanGuardian, GenderEnum, OrphanBalance, GuardianBalance,
    GuardianTransaction,
    Transaction, User, PermissionEnum
)
from utils import log_activity, parse_and_validate_date, try_get_date, parse_decimal
from services.db_services import DBService
from controllers import PersonController, PaginationController
from components import AddTransactionDialog, DeceasedSearchDialog, ExportReportDialog, GuardianSearchDialog, OrphanSearchDialog
from services.permissions import has_permission
from services.reporting import generate_report
from utils.distribution import calculate_beneficiary_distribution, to_decimal_money

warnings.filterwarnings("ignore", category=DeprecationWarning)

# إعداد نظام السجلات
logger = logging.getLogger(__name__)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

# Now use the function to find your UI files
FORM_CLASS, _ = loadUiType(resource_path(os.path.join("ui", "app.ui")))
FORM_CLASS2, _ = loadUiType(resource_path(os.path.join("ui", "login.ui")))


class ResourceTypes:
    # الموارد الأساسية
    DECEASED = "deceased"       # المتوفى
    ORPHAN = "orphan"           # اليتيم
    GUARDIAN = "guardian"       # الوصي
    
    # العلاقات والروابط
    ORPHAN_GUARDIAN = "orphan_guardian_link"  # علاقة اليتيم بالوصي
    DECEASED_GUARDIAN = "deceased_guardian"   # علاقة المتوفى بالوصي
    
    # المعاملات المالية
    DECEASED_TRANSACTION = "deceased_transaction"  # جدول حركات المتوفين
    ORPHAN_TRANSACTION = "orphan_transaction"      # جدول حركات الأيتام
    BALANCE = "balance"         # رصيد
    CURRENCY = "currency"       # عملة
    
    # النظام
    USER = "user"               # مستخدم (موظف)
    ROLE = "role"               # دور
    PERMISSION = "permission"   # صلاحية
    ACTIVITY_LOG = "activity_log" # سجل النشاطات
    SETTINGS = "settings"

ar_resource_types = {
    # الموارد الأساسية
    ResourceTypes.DECEASED: "متوفى",
    ResourceTypes.ORPHAN: "يتيم",
    ResourceTypes.GUARDIAN: "وصي",

    # العلاقات والروابط
    ResourceTypes.ORPHAN_GUARDIAN: "رابط اليتيم بالوصي",
    ResourceTypes.DECEASED_GUARDIAN: "رابط المتوفى بالوصي",

    # المعاملات المالية
    ResourceTypes.DECEASED_TRANSACTION: "حركة مالية للمتوفى",
    ResourceTypes.ORPHAN_TRANSACTION: "حركة مالية لليتيم",
    ResourceTypes.BALANCE: "الرصيد",
    ResourceTypes.CURRENCY: "العملة",

    # النظام
    ResourceTypes.USER: "مستخدم",
    ResourceTypes.ROLE: "دور (صلاحية مجموعة)",
    ResourceTypes.PERMISSION: "صلاحية محددة",
    ResourceTypes.ACTIVITY_LOG: "سجل النشاطات",
    ResourceTypes.SETTINGS: "الإعدادات"
}

class ActionTypes:
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

# ===== Person Types =====
class PersonType:
    ORPHAN = "orphan"
    DECEASED = "deceased"
    GUARDIAN = "guardian"

class LoginWindow(QMainWindow, FORM_CLASS2):
    shown = False
    login_success_signal = pyqtSignal(object)
    
    def __init__(self, db_service):
        super().__init__()
        self.setupUi(self)
        self.db_service = db_service
        
        # تعيين عنوان النافذة
        self.setWindowTitle("نظام إدارة الأيتام - تسجيل الدخول")
        
        # تأجيل تحميل الأيقونة إلى ما بعد عرض النافذة (لتسريع البدء)
        self.icon_loaded = False
        
        self.login_btn.clicked.connect(self.handle_login)
    
    def _load_icon_async(self):
        """تحميل الأيقونة بشكل متأخر بعد عرض النافذة"""
        if not self.icon_loaded:
            from database.db import get_application_icon
            icon = get_application_icon()
            if icon:
                self.setWindowIcon(icon)
            self.icon_loaded = True
    
    def showEvent(self, event):
        super().showEvent(event)
        if not self.shown:
            self.shown = True
            self.setStyleSheet(self.styleSheet())
            # تحميل الأيقونة بعد عرض النافذة للسرعة
            QTimer.singleShot(50, self._load_icon_async)
    
    def handle_login(self):
        # تفريغ الرسالة السابقة وتغيير لونها (مثلاً أحمر للأخطاء)
        self.msg.setText("")
        self.msg.setStyleSheet("color: red; font-weight: bold;") 

        username = self.username.text().strip()
        password = self.password.text().strip()

        if not username or not password:
            self.msg.setText("يرجى إدخال اسم المستخدم وكلمة المرور.")
            return

        db = self.db_service.session
        try:
            user = db.query(User).filter_by(username=username).first()

            if user:
                # التحقق من كلمة المرور
                if bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
                    # في حالة النجاح، نغير اللون للأخضر
                    self.msg.setStyleSheet("color: green; font-weight: bold;")
                    self.msg.setText("تم تسجيل الدخول بنجاح! جاري التحميل...")
                    
                    # تنفيذ عملية فتح النافذة الرئيسية بعد تأخير بسيط أو مباشرة
                    if hasattr(self, 'login_success_signal'):
                        self.login_success_signal(user)
                else:
                    raise ValueError("كلمة المرور غير صحيحة.")
            else:
                raise ValueError("اسم المستخدم غير موجود.")

        except ValueError as ve:
            # عرض الخطأ داخل الـ Label بدلاً من QMessageBox
            self.msg.setText(str(ve))
        except Exception as e:
            QMessageBox.warning(self, "خطأ", str(e))

# ===== Main Window =====
class MainWindow(QMainWindow, FORM_CLASS):
    shown = False
    logout_signal = pyqtSignal()

    def __init__(self, db_service):
        super().__init__()
        self.setupUi(self)
        # self.setFixedSize(1080, 690)
        self.current_user = None
        
        self.d_orphans = []  # لتخزين الأيتام المرتبطين بالمتوفى الحالي في صفحة التفاصيل
        self.current_deceased_for_t_table = None  # لتخزين المتوفى الحالي لجدول المعاملات
        self.current_primary_guardian_for_t_table = None
        self.current_primary_guardian_orphan_id_for_t_table = None
        self.t_table_entities = []
        self._t_table_default_column_widths = {}
        self._t_table_width_shortcuts = []
        self._excel_shortcuts_registry = {}
        
        # تعيين عنوان النافذة
        self.setWindowTitle("نظام إدارة الأيتام - لوحة التحكم")
        
        # تأجيل تحميل الأيقونة (لتسريع البدء)
        self.icon_loaded = False
        
        self.init_ui()
        
        self.navigation_back_stack = []
        self.navigation_forward_stack = []
        self._is_navigating = False # علم لمنع تسجيل التنقل أثناء الضغط على زر رجوع نفسه
        
        self.backup_manager = BackupManager(self)
        self.deceased_pagination = PaginationController()
        self.guardians_pagination = PaginationController()
        self.orphans_pagination = PaginationController()
        self.orphans_older_or_equal_18_pagination = PaginationController()
        self.activity_log_pagination = PaginationController()
        self.db_service = db_service
        self.controller = PersonController(self.db_service)

        self.init_dashboard()
        # === Tab Router (dynamic) ===
        self.init_tab_router()

        ### === Signals === ###
        # === Show Detail Page Signals ===
        self.show_edit_page_deceased_btn.clicked.connect(
            lambda: self.open_person(self.controller.current_person.deceased, PersonType.DECEASED) if self.controller.current_person else None
        )
        self.show_edit_page_guardian_btn.clicked.connect(self.open_primary_guardian_from_orphan)
        self.show_edit_page_guardian_btn_2.clicked.connect(self.open_guardian_from_deceased)
        
        # === Detail Page Action Buttons Signals ===
        self.detail_delete_btn.clicked.connect(
            lambda: self.delete_person_record(self.controller.current_person)
        )
        self.detail_save_btn.clicked.connect(
            lambda: self.save_person_record(self.controller.current_person)
        )
        
        # === Pagination Signals ===
        self.next_btn.clicked.connect(self.next_page)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn_2.clicked.connect(self.next_page)
        self.prev_btn_2.clicked.connect(self.prev_page)
        self.next_btn_3.clicked.connect(self.next_page)
        self.prev_btn_3.clicked.connect(self.prev_page)
        self.next_btn_4.clicked.connect(self.next_page)
        self.prev_btn_4.clicked.connect(self.prev_page)
        self.next_btn_5.clicked.connect(self.next_page)
        self.prev_btn_5.clicked.connect(self.prev_page)

        # === Search Signals ===
        self.search_btn.clicked.connect(self.search_by_id_or_name)
        self.btn_search_guardian.clicked.connect(self.search_guardian_by_id_or_name)
        self.btn_search_guardian_2.clicked.connect(self.search_guardian_by_id_or_name_2)
        self.btn_search_guardian_3.clicked.connect(self.search_guardian_by_id_or_name_3)
        self.btn_search_guardian_4.clicked.connect(self.search_guardian_by_id_or_name_4)
        self.btn_search_deceased.clicked.connect(self.search_deceased_by_id_or_name)
        self.btn_search_deceased_2.clicked.connect(self.search_deceased_by_id_or_name_2)
        self.btn_search_orphan.clicked.connect(
            lambda: self.search_orphan_by_id_or_name(self.add_deceased_orphans_table, 'deceased')
        )
        self.btn_search_orphan_2.clicked.connect(
            lambda: self.search_orphan_by_id_or_name(self.add_guardian_orphans_table)
        )
        self.btn_search_orphan_3.clicked.connect(
            lambda: self.search_orphan_by_id_or_name(self.detail_deceased_orphans_table, 'deceased')
        )
        self.btn_search_orphan_4.clicked.connect(
            lambda: self.search_orphan_by_id_or_name_2(self.detail_guardian_orphans_table)
        )

        # === Add New Records Signals ===
        self.add_new_deceased_btn.clicked.connect(self.add_new_deceased)
        self.add_new_orphan_btn.clicked.connect(self.add_new_orphan)
        self.add_new_guardian_btn.clicked.connect(self.add_new_guardian)
        
        # === Transaction Table Buttons Signals ===
        self.btn_add_trans_row.clicked.connect(
            lambda: self.add_row_transaction_table(self.detail_orphan_transactions_table)
        )
        self.btn_remove_trans_row.clicked.connect(
            lambda: self.remove_selected_row_transaction_table(self.detail_orphan_transactions_table)
        )
        # self.btn_add_trans_row_2.clicked.connect(self.add_deceased_transaction_row)
        self.btn_remove_trans_row_2.clicked.connect(self.remove_deceased_transaction_row)
        self.btn_add_trans_row_2.clicked.connect(self.open_add_transaction_dialog)
        self.btn_add_trans_row_3.clicked.connect(self.add_guardian_transaction_row)
        self.btn_remove_trans_row_3.clicked.connect(self.remove_guardian_transaction_row)
        
        # === Orphans Table Buttons Signals ===
        self.add_deceased_orphans_table_btn.clicked.connect(
            lambda: self.add_row_to_orphans_table(self.add_deceased_orphans_table, False)
        )
        self.remove_deceased_orphans_table_btn.clicked.connect(
            lambda: self.remove_selected_orphan_row(self.add_deceased_orphans_table)
        )
        self.add_guardian_orphans_table_btn_3.clicked.connect(
            lambda: self.add_row_to_orphans_table(self.add_guardian_orphans_table)
        )
        self.remove_guardian_orphans_table_btn.clicked.connect(
            lambda: self.remove_selected_orphan_row(self.add_guardian_orphans_table)
        )
        self.add_deceased_orphans_table_btn_2.clicked.connect(
            lambda: self.add_row_to_orphans_table(self.detail_deceased_orphans_table)
        )
        self.remove_deceased_orphans_table_btn_2.clicked.connect(
            lambda: self.remove_selected_orphan_row(self.detail_deceased_orphans_table)
        )
        self.add_guardian_orphans_table_btn_4.clicked.connect(
            lambda: self.add_row_to_orphans_table(self.detail_guardian_orphans_table)
        )
        self.remove_guardian_orphans_table_btn_3.clicked.connect(
            lambda: self.remove_selected_orphan_row(self.detail_guardian_orphans_table)
        )
        
        # === Backup Signals ===
        self.btn_backup.clicked.connect(self.backup_manager.execute_backup)
        self.btn_restore_backup.clicked.connect(self.backup_manager.execute_restore)
        
        # === Tab Change Signals ===
        self.person_record_tabs.currentChanged.connect(self.on_tab_changed)
        self.tabWidget.currentChanged.connect(self.on_main_tab_changed)
        self.add_person_record_tabs.currentChanged.connect(self.on_add_person_record_tabs_changed)
        self.on_add_person_record_tabs_changed(self.add_person_record_tabs.currentIndex())
        self.on_users_tabs_changed(self.tabWidget_3.currentIndex())
        
        # === Table row clicked ===
        self.deceased_people_table.cellDoubleClicked.connect(self.on_deceased_row_double_clicked)
        self.guardians_table.cellDoubleClicked.connect(self.on_guardian_row_double_clicked)
        # الجدول الأول
        self.orphans_table.cellDoubleClicked.connect(
            lambda row, col: self.on_orphan_row_double_clicked(row, col, self.orphans_table)
        )

        # الجدول الثاني (أيتام أكبر من 18)
        self.orphans_older_or_equal_18_table.cellDoubleClicked.connect(
            lambda row, col: self.on_orphan_row_double_clicked(row, col, self.orphans_older_or_equal_18_table)
        )
        self.roles_table.cellDoubleClicked.connect(self.on_role_row_clicked)
        
        self.pushButton.clicked.connect(self.create_user)
        self.pushButton_2.clicked.connect(self.update_user)
        self.clear_user_update_btn.clicked.connect(self.clear_user_inputs)
        self.show_user_btn.clicked.connect(self.show_user_detail)
        self.role_save_btn.clicked.connect(self.save_role)
        self.role_delete_btn.clicked.connect(self.delete_role)
        
        self.roles_combo.currentIndexChanged.connect(self.load_permissions)
        self.save_permissions_btn.clicked.connect(self.save_permissions)
        self.check_all_btn.clicked.connect(self.check_all)
        self.uncheck_all_btn.clicked.connect(self.uncheck_all)
        
        self.detail_export_btn.clicked.connect(
            lambda: self.export_person_record(self.controller.current_person)
        )
        
        self.orphans_monthly_report.clicked.connect(self.open_export_popup)
        self.comboBox.currentIndexChanged.connect(self.toggle_deceased_ils_inputs)
        self.comboBox_2.currentIndexChanged.connect(self.toggle_deceased_usd_inputs)
        self.comboBox_3.currentIndexChanged.connect(self.toggle_deceased_jod_inputs)
        self.comboBox_4.currentIndexChanged.connect(self.toggle_deceased_eur_inputs)
        # عند تغيير الاختيار في الراديو بوتون، نفذ الدالة فوراً
        self.buttonGroup.buttonClicked.connect(self.update_table_editing_mode)
        
        self.logout_btn.clicked.connect(self.handle_logout)
        
        self.role_id_input.textChanged.connect(
            lambda text: self.role_delete_btn.setEnabled(bool(text.strip()))
        )
        self.role_name_input.textChanged.connect(
            lambda text: self.role_id_input.clear() if not text.strip() else None
        )
        
        self.search_btn_2.clicked.connect(self.open_deceased_selection_dialog)

        currencies = self.db_service.session.query(Currency.name, Currency.id).all()
        for text, data in currencies:
            self.c_combo.addItem(text, data)
        # when currency changes, reload historical data if a deceased is active
        self.c_combo.currentIndexChanged.connect(self.on_currency_changed)
        
        self.add_new_row_t_btn.clicked.connect(self.add_row_to_t_table)
        if hasattr(self, "add_new_row_to_t_table_btn"):
            self.add_new_row_to_t_table_btn.clicked.connect(self.open_add_t_table_row_dialog)
        self.remove_selected_row_t_btn.clicked.connect(self.remove_selected_row_from_t_table)
        self.t_table.cellDoubleClicked.connect(self.on_t_table_cell_double_clicked)
        if hasattr(self, "reload_trans_table"):
            self.reload_trans_table.clicked.connect(self.reload_transactions_table)
        
        # تعطيل الأزرار في البداية (الجدول فارغ)
        self.add_new_row_t_btn.setEnabled(False)
        if hasattr(self, "add_new_row_to_t_table_btn"):
            self.add_new_row_to_t_table_btn.setEnabled(False)
        self.remove_selected_row_t_btn.setEnabled(False)
        
        self.pushButton_3.clicked.connect(self.save_transactions)
        if hasattr(self, "open_table_window"):
            self.open_table_window.clicked.connect(self.open_t_table_fullscreen_editor)
    
    def open_deceased_selection_dialog(self):
        # جلب النص من حقل البحث (اسم، هوية، أو أرشيف 10866)
        search_term = self.lineEdit_42.text().strip()
        
        if not search_term:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال نص للبحث أولاً.")
            return

        # إنشاء النافذة المنبثقة للبحث
        # تأكد أن DeceasedSearchDialog مهيأة لاستقبال الـ session و نص البحث
        dialog = DeceasedSearchDialog(self.db_service.session, search_term)
        
        if dialog.exec():  # إذا اختار المستخدم شخصاً وضغط "موافق"
            selected_deceased = dialog.get_selected_deceased()
            if selected_deceased:
                # تحديث حقل البحث باسم المختار
                self.lineEdit_42.setText(selected_deceased.name)
                # استدعاء دالة تحديث جدول الأرصدة والأيتام
                self.d_orphans = selected_deceased.orphans  # تخزين الأيتام المرتبطين بالمتوفى الحالي
                self.current_deceased_for_t_table = selected_deceased  # حفظ المتوفى الحالي
                self.load_historical_data_for_deceased(selected_deceased)
    
    def load_historical_data_for_deceased(self, deceased):
        """تجهيز الجدول بدمج أعمدة الإيداع والسحب تحت اسم كل يتيم مع تنسيق كامل
        بالإضافة لملء السجلات السابقة من قاعدة البيانات إن وجدت."""
        try:
            # حفظ حالة عمود تفاصيل المتوفي قبل إعادة التحميل حتى لا يضيع رقم الحركة
            previous_action_by_row_key = {}
            if self.t_table.columnCount() >= 3:
                try:
                    _, _, previous_action_col, _, _ = self._get_financial_table_special_columns(self.t_table)
                    for r in range(2, self.t_table.rowCount()):
                        id_item_prev = self.t_table.item(r, 0)
                        action_item_prev = self.t_table.item(r, previous_action_col)
                        if not id_item_prev:
                            continue
                        row_key_prev = id_item_prev.data(Qt.ItemDataRole.UserRole)
                        if not row_key_prev or not action_item_prev:
                            continue
                        payload_prev = action_item_prev.data(Qt.ItemDataRole.UserRole)
                        text_prev = action_item_prev.text() if action_item_prev else ""
                        previous_action_by_row_key[row_key_prev] = {
                            "text": text_prev,
                            "payload": payload_prev,
                        }
                except Exception:
                    previous_action_by_row_key = {}

            # تخزين الأيتام للاستخدام لاحقاً (مثل الحفظ أو الحساب)
            self.d_orphans = deceased.orphans
            self.current_primary_guardian_for_t_table = self.get_guardian_from_deceased(deceased)
            self.current_primary_guardian_orphan_id_for_t_table = None
            guardian_relation = ""
            if self.current_primary_guardian_for_t_table:
                for orphan in deceased.orphans:
                    if not orphan.guardian_links:
                        continue
                    primary_link = next((l for l in orphan.guardian_links if l.is_primary), orphan.guardian_links[0])
                    if primary_link and primary_link.guardian_id == self.current_primary_guardian_for_t_table.id:
                        self.current_primary_guardian_orphan_id_for_t_table = primary_link.orphan_id
                        guardian_relation = primary_link.relation or ""
                        break

            # 1. إعداد هيكلية الأعمدة بناءً على عدد الأيتام
            orphans = self.d_orphans
            entities = [{"kind": "orphan", "id": o.id, "name": o.name} for o in orphans]
            if self.current_primary_guardian_for_t_table:
                entities.append({
                    "kind": "guardian",
                    "id": self.current_primary_guardian_for_t_table.id,
                    "name": self.current_primary_guardian_for_t_table.name,
                })
            self.t_table_entities = entities

            # الأعمدة: ID + تاريخ + تفاصيل المتوفي + (2 لكل كيان) + الرصيد الكلي + ملاحظة + حذف
            total_cols = 6 + (len(entities) * 2)
            self.t_table.setColumnCount(total_cols)
            self.t_table.setColumnHidden(0, True)
            total_col, note_col, action_col, delete_col, entity_start_col = self._get_financial_table_special_columns(self.t_table)
            
            # استخدام أول صفين كعناوين (Headers) لمحاكاة التصميم المطلوب
            self.t_table.setRowCount(2) 
            
            # 2. دمج وتسمية العناوين الثابتة (ID وتاريخ الحركة)
            static_headers = {0: "ID", 1: "تاريخ الحركة", action_col: "تفاصيل المتوفي"}
            for col, text in static_headers.items():
                self.t_table.setSpan(0, col, 2, 1) # دمج صفين رأسياً
                item = QTableWidgetItem(text)
                self.t_table.setItem(0, col, item)

            # 3. بناء أعمدة الأيتام المدمجة (إيداع وسحب)
            col_idx = entity_start_col
            col_map = {}
            for entity in entities:
                entity_key = (entity["kind"], entity["id"])
                col_map[entity_key] = col_idx

                full_name = (entity.get("name") or "").strip()
                display_name = full_name.split()[0] if full_name else ""

                # دمج اسم اليتيم أفقياً فوق عمودي الإيداع والسحب
                self.t_table.setSpan(0, col_idx, 1, 2) 
                if entity["kind"] == "orphan":
                    header_title = display_name
                else:
                    relation_text = guardian_relation.strip()
                    if relation_text:
                        header_title = f"{display_name}\n( {relation_text} )"
                    else:
                        header_title = display_name
                entity["header_title"] = header_title
                name_item = QTableWidgetItem(header_title)
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.t_table.setItem(0, col_idx, name_item)
                
                # العناوين الفرعية في الصف الثاني (إيداع / سحب)
                deposit_item = QTableWidgetItem("إيداع (+)")
                deposit_item.setBackground(QColor("#c8e6c9"))  # light green
                deposit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                deposit_item.setForeground(QColor("black"))
                self.t_table.setItem(1, col_idx, deposit_item)
                withdraw_item = QTableWidgetItem("سحب (-)")
                withdraw_item.setBackground(QColor("#ffcdd2"))  # light red
                withdraw_item.setForeground(QColor("red"))
                withdraw_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.t_table.setItem(1, col_idx + 1, withdraw_item)
                
                name_len = len(display_name)
                adaptive_width = max(75, min(120, 60 + (name_len * 6)))
                if entity["kind"] == "guardian":
                    adaptive_width = min(adaptive_width + 10, 130)
                self.t_table.setColumnWidth(col_idx, adaptive_width)
                self.t_table.setColumnWidth(col_idx + 1, adaptive_width)
                
                col_idx += 2

            # 4. العناوين النهائية (الرصيد والملاحظة)
            last_headers = {
                total_col: "الرصيد الكلي",
                note_col: "ملاحظة",
                delete_col: "حذف",
            }
            for col, text in last_headers.items():
                self.t_table.setSpan(0, col, 2, 1)
                self.t_table.setItem(0, col, QTableWidgetItem(text))

            # 5. تنسيق الخلايا (0 و 1) لتبدو كشريط عناوين رسمي (Header Style)
            for r in range(2):
                for c in range(self.t_table.columnCount()):
                    item = self.t_table.item(r, c)
                    if item:
                        item.setBackground(QColor("#f3f4f6")) 
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # 6. إعدادات المظهر النهائي للجدول
            self.t_table.horizontalHeader().setVisible(False)
            self.t_table.setWordWrap(True)
            self.t_table.setTextElideMode(Qt.TextElideMode.ElideNone)
            self.t_table.setRowHeight(0, 80)
            self.t_table.setStyleSheet(
                "QTableWidget { gridline-color: #d0d0d0; }"
                "QTableWidget::item:selected {"
                " background-color: #e8f0ff;"
                " color: black;"
                " border: 1px solid #2563eb;"
                "}"
            )
            header = self.t_table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
            self.t_table.setColumnWidth(note_col, 240)
            self.t_table.setColumnWidth(action_col, 170)
            self.t_table.setColumnWidth(delete_col, 90)
            self._t_table_default_column_widths = {
                c: self.t_table.columnWidth(c) for c in range(self.t_table.columnCount())
            }

            # ربط signal لحساب الرصيد الكلي تلقائياً عند تغيير أي خلية
            try:
                self.t_table.itemChanged.disconnect(self.on_t_table_cell_changed)
            except Exception:
                pass
            self.t_table.itemChanged.connect(self.on_t_table_cell_changed)

            # إضافة الصفوف الحالية من قاعدة البيانات
            if entities:
                orphan_ids = [o.id for o in orphans]
                db = self.db_service.session
                currency_id = self.c_combo.currentData()
                history_rows = []

                if orphan_ids:
                    query = db.query(Transaction).filter(Transaction.orphan_id.in_(orphan_ids))
                    if currency_id:
                        query = query.filter(Transaction.currency_id == currency_id)
                    orphan_txns = query.order_by(Transaction.created_at).all()
                    for txn in orphan_txns:
                        history_rows.append({
                            "kind": "orphan",
                            "person_id": txn.orphan_id,
                            "txn": txn,
                        })

                if self.current_primary_guardian_for_t_table:
                    g_query = db.query(GuardianTransaction).filter(
                        GuardianTransaction.guardian_id == self.current_primary_guardian_for_t_table.id,
                        GuardianTransaction.deceased_id == self.current_deceased_for_t_table.id,
                    )
                    if currency_id:
                        g_query = g_query.filter(GuardianTransaction.currency_id == currency_id)
                    guardian_txns = g_query.order_by(GuardianTransaction.created_date).all()
                    for txn in guardian_txns:
                        history_rows.append({
                            "kind": "guardian",
                            "person_id": txn.guardian_id,
                            "txn": txn,
                        })

                history_rows.sort(
                    key=lambda rec: getattr(rec["txn"], "created_at", None) or rec["txn"].created_date
                )

                # group transactions by exact datetime string to collapse simultaneous entries
                grouped = {}
                for rec in history_rows:
                    txn = rec["txn"]
                    tx_dt = getattr(txn, "created_at", None) or txn.created_date
                    tx_group_key = (getattr(txn, "row_group_key", None) or "").strip()
                    if tx_group_key:
                        key = tx_group_key
                        if key not in grouped:
                            grouped[key] = []
                        grouped[key].append(rec)
                        continue
                    if not tx_dt:
                        continue
                    key = self._format_row_datetime_key(tx_dt)
                    if key not in grouped:
                        grouped[key] = []
                    grouped[key].append(rec)

                for key, tx_list in grouped.items():
                    row = self.t_table.rowCount()
                    self.t_table.insertRow(row)
                    # use first txn id as representative (could be changed)
                    first_txn = tx_list[0]["txn"]
                    prefix = "O" if tx_list[0]["kind"] == "orphan" else "G"
                    id_item = QTableWidgetItem(f"{prefix}-{first_txn.id}")
                    id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    id_item.setData(Qt.ItemDataRole.UserRole, key)
                    self.t_table.setItem(row, 0, id_item)
                    # التاريخ (use key or first txn date)
                    first_dt = getattr(first_txn, "created_date", None) or getattr(first_txn, "created_at", None)
                    date_item = QTableWidgetItem(first_dt.strftime("%d/%m/%Y") if first_dt else "")
                    date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.t_table.setItem(row, 1, date_item)

                    # aggregate amounts per orphan/guardian for this timestamp
                    sums = {}
                    for rec in tx_list:
                        txn = rec["txn"]
                        entity_key = (rec["kind"], rec["person_id"])
                        if entity_key not in sums:
                            sums[entity_key] = {"deposit": 0, "withdraw": 0}
                        if txn.type == TransactionTypeEnum.deposit:
                            sums[entity_key]["deposit"] += float(txn.amount)
                        else:
                            sums[entity_key]["withdraw"] += float(txn.amount)

                    for entity_key, values in sums.items():
                        if entity_key in col_map:
                            base = col_map[entity_key]
                            if values["deposit"]:
                                dep_item = QTableWidgetItem(f"{values['deposit']:,.2f}")
                                dep_item.setBackground(QColor("#c8e6c9"))
                                dep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                                dep_item.setForeground(QColor("black"))
                                self.t_table.setItem(row, base, dep_item)
                            if values["withdraw"]:
                                w_item = QTableWidgetItem(f"{values['withdraw']:,.2f}")
                                w_item.setBackground(QColor("#ffcdd2"))
                                w_item.setForeground(QColor("black"))
                                w_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                                self.t_table.setItem(row, base + 1, w_item)

                    # تجميع الملاحظات من كل المعاملات في هذا الصف
                    # notes = [txn.note for txn in tx_list if txn.note]
                    # combined_notes = " | ".join(notes) if notes else ""
                    notes_item = QTableWidgetItem(self._sanitize_user_visible_note(first_txn.note))
                    notes_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.t_table.setItem(row, note_col, notes_item)

                    linked_deceased_txn_id = None
                    display_deceased_txn_id = None
                    for rec in tx_list:
                        tx_obj = rec.get("txn")
                        if rec.get("kind") == "orphan" and getattr(tx_obj, "deceased_transaction_id", None):
                            linked_deceased_txn_id = tx_obj.deceased_transaction_id
                            break

                    # fallback: في التوزيع اليدوي لا يتم حفظ deceased_transaction_id على معاملات الأيتام/الوصي.
                    # نربط فقط عبر row_group_key لتجنب الربط الخاطئ لصفوف مستقلة بنفس التاريخ.
                    if not linked_deceased_txn_id and self.current_deceased_for_t_table:
                        row_group_key = getattr(first_txn, "row_group_key", None)
                        if row_group_key:
                            fallback_query = db.query(DeceasedTransaction).filter(
                                DeceasedTransaction.deceased_id == self.current_deceased_for_t_table.id,
                                DeceasedTransaction.row_group_key == row_group_key,
                            )
                            if currency_id:
                                fallback_query = fallback_query.filter(DeceasedTransaction.currency_id == currency_id)

                            fallback_txn = fallback_query.filter(
                                DeceasedTransaction.is_auto_manual_distribution == False,
                            ).order_by(DeceasedTransaction.id.desc()).first()

                            if not fallback_txn:
                                fallback_txn = fallback_query.order_by(DeceasedTransaction.id.desc()).first()

                            if fallback_txn:
                                linked_deceased_txn_id = fallback_txn.id

                    if linked_deceased_txn_id:
                        anchor_txn = db.query(DeceasedTransaction).filter_by(id=linked_deceased_txn_id).first()
                        if anchor_txn and anchor_txn.type == TransactionTypeEnum.withdraw:
                            paired_deposit = db.query(DeceasedTransaction).filter(
                                DeceasedTransaction.id != anchor_txn.id,
                                DeceasedTransaction.deceased_id == anchor_txn.deceased_id,
                                DeceasedTransaction.currency_id == anchor_txn.currency_id,
                                DeceasedTransaction.amount == anchor_txn.amount,
                                DeceasedTransaction.type == TransactionTypeEnum.deposit,
                            ).order_by(DeceasedTransaction.id.desc()).first()
                            display_deceased_txn_id = paired_deposit.id if paired_deposit else linked_deceased_txn_id
                        else:
                            display_deceased_txn_id = linked_deceased_txn_id

                    if linked_deceased_txn_id:
                        action_item = self._create_t_table_deceased_action_item(
                            f"تمت الإضافة #{display_deceased_txn_id}",
                            {
                                "status": "saved",
                                "txn_id": display_deceased_txn_id,
                                "distribution_anchor_txn_id": linked_deceased_txn_id,
                            },
                        )
                        self._set_t_table_row_entity_editable(row, editable=False)
                    else:
                        preserved = previous_action_by_row_key.get(key)
                        preserved_payload = preserved.get("payload") if preserved else None
                        if isinstance(preserved_payload, dict) and preserved_payload.get("status") == "saved":
                            action_item = self._create_t_table_deceased_action_item(
                                preserved.get("text") or "إضافة تفاصيل",
                                preserved_payload,
                            )
                        else:
                            action_item = self._create_t_table_deceased_action_item()
                        self._set_t_table_row_entity_editable(row, editable=True)
                    self.t_table.setItem(row, action_col, action_item)
                    self.t_table.setItem(row, delete_col, self._create_t_table_delete_item())

                # حساب الأرصدة لكل صف بعد ملئ البيانات
                for r in range(2, self.t_table.rowCount()):
                    total_balance = 0.0
                    for c in range(entity_start_col, total_col):
                        item = self.t_table.item(r, c)
                        if item and item.text().strip():
                            try:
                                val = float(item.text().replace(',', ''))
                                if (c - entity_start_col) % 2 == 0:
                                    total_balance += val
                                else:
                                    total_balance -= val
                            except ValueError:
                                pass
                    w_item = QTableWidgetItem(f"{total_balance:,.2f}")
                    w_item.setBackground(QColor("#e0e0e0"))  # light gray background
                    w_item.setForeground(QColor("black"))
                    w_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.t_table.setItem(r, total_col, w_item)

            # تحديث حالة الأزرار (سيكون الجدول فارغاً في البداية)
            self.update_t_table_buttons_state()
            self._refresh_financial_entity_header_balances(self.t_table)

        except Exception as e:
            print(f"حدث خطأ أثناء تحديث الجدول: {e}")

    def on_currency_changed(self):
        """Reload historical table when the selected currency changes."""
        # reload if deceased is loaded in t_table context
        if self.current_deceased_for_t_table:
            self.load_historical_data_for_deceased(self.current_deceased_for_t_table)
        # or if viewing deceased details page
        elif hasattr(self.controller, 'current_person') and self.controller.current_person:
            if self.controller.current_type == PersonType.DECEASED:
                self.load_historical_data_for_deceased(self.controller.current_person)

    def reload_transactions_table(self):
        """Manual reload action for transactions table."""
        if self.current_deceased_for_t_table:
            self.load_historical_data_for_deceased(self.current_deceased_for_t_table)
        elif hasattr(self.controller, 'current_person') and self.controller.current_person:
            if self.controller.current_type == PersonType.DECEASED:
                self.current_deceased_for_t_table = self.controller.current_person
                self.load_historical_data_for_deceased(self.controller.current_person)
            else:
                QMessageBox.warning(self, "تنبيه", "يرجى اختيار متوفى أولاً لإعادة تحميل الجدول.")
        else:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار متوفى أولاً لإعادة تحميل الجدول.")
    
    def on_t_table_cell_changed(self, item):
        """حساب الرصيد الكلي عند تغيير قيمة الإيداع أو السحب"""
        if not item:
            return
        self.recalculate_financial_row_balance(self.t_table, item.row())

    def _get_financial_table_special_columns(self, table: QTableWidget):
        action_col = 2
        entity_start_col = 3
        total_col = table.columnCount() - 3
        note_col = table.columnCount() - 2
        delete_col = table.columnCount() - 1
        return total_col, note_col, action_col, delete_col, entity_start_col

    def _create_t_table_deceased_action_item(self, text: str = "إضافة تفاصيل", payload=None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setBackground(QColor("#f3f4f6"))
        item.setData(Qt.ItemDataRole.UserRole, payload)
        return item

    def _create_t_table_delete_item(self):
        item = QTableWidgetItem("حذف")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setForeground(QColor("#b91c1c"))
        item.setBackground(QColor("#fef2f2"))
        return item

    def _format_row_datetime_key(self, dt_value):
        if not dt_value:
            return ""
        return dt_value.strftime("%Y-%m-%d %H:%M:%S.%f")

    def _parse_row_datetime_key(self, row_key):
        key_text = str(row_key or "").strip()
        if not key_text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(key_text, fmt)
            except ValueError:
                continue
        return None

    def _sanitize_user_visible_note(self, note_text: str) -> str:
        """Normalize note text before displaying to user."""
        return str(note_text or "").strip()

    def _build_deceased_payload_from_txn(self, txn: DeceasedTransaction):
        txn_type = "deposit" if txn.type == TransactionTypeEnum.deposit else "withdraw"
        currency_code = txn.currency.code if txn.currency and txn.currency.code else ""
        return {
            "deceased_id": txn.deceased_id,
            "currency_id": txn.currency_id,
            "currency_code": currency_code,
            "amount": Decimal(str(txn.amount or 0)),
            "type": txn_type,
            "receipt_number": txn.receipt_number or "",
            "payer_name": txn.payer_name or "",
            "payment_method": txn.payment_method or "نقداً",
            "check_number": txn.check_number or "",
            "bank_name": txn.bank_name or "",
            "due_date": txn.due_date,
            "reference_number": txn.reference_number or "",
            "should_distribute": False,
            "distribution_mode": "بالتساوي",
            "include_guardian_share": False,
            "note": self._sanitize_user_visible_note(txn.note),
            "date_text": txn.created_date.strftime("%d/%m/%Y") if txn.created_date else "",
        }

    def _normalize_deceased_payload_for_compare(self, payload: dict):
        if not isinstance(payload, dict):
            return {}

        due_date = payload.get("due_date")
        if hasattr(due_date, "isoformat"):
            due_date_value = due_date.isoformat()
        else:
            due_date_value = str(due_date or "").strip()

        amount_value = payload.get("amount")
        try:
            amount_value = str(Decimal(str(amount_value or 0)).quantize(Decimal("0.01")))
        except Exception:
            amount_value = str(amount_value or "").strip()

        normalized = {
            "deceased_id": payload.get("deceased_id"),
            "currency_id": payload.get("currency_id"),
            "amount": amount_value,
            "type": str(payload.get("type") or "").strip(),
            "receipt_number": str(payload.get("receipt_number") or "").strip(),
            "payer_name": str(payload.get("payer_name") or "").strip(),
            "payment_method": str(payload.get("payment_method") or "").strip(),
            "check_number": str(payload.get("check_number") or "").strip(),
            "bank_name": str(payload.get("bank_name") or "").strip(),
            "due_date": due_date_value,
            "reference_number": str(payload.get("reference_number") or "").strip(),
            "should_distribute": bool(payload.get("should_distribute")),
            "distribution_mode": str(payload.get("distribution_mode") or "").strip(),
            "include_guardian_share": bool(payload.get("include_guardian_share")),
            "note": str(payload.get("note") or "").strip(),
        }
        return normalized

    def _prefill_add_transaction_dialog(self, dialog: AddTransactionDialog, payload: dict):
        if not payload:
            return

        currency_code = payload.get("currency_code")
        if not currency_code and payload.get("currency_id"):
            c_obj = self.db_service.session.query(Currency).get(payload.get("currency_id"))
            currency_code = c_obj.code if c_obj and c_obj.code else None
        if currency_code:
            idx = dialog.combo_currency.findText(currency_code)
            if idx >= 0:
                dialog.combo_currency.setCurrentIndex(idx)

        t_text = "إيداع" if payload.get("type") == "deposit" else "سحب"
        t_idx = dialog.combo_type.findText(t_text)
        if t_idx >= 0:
            dialog.combo_type.setCurrentIndex(t_idx)

        try:
            dialog.amount_input.setValue(min(abs(float(payload.get("amount") or 0)), 9_999_999.99))
        except Exception:
            pass

        date_text = (payload.get("date_text") or "").strip()
        if date_text and QDate.fromString(date_text, "dd/MM/yyyy").isValid():
            dialog.date_input.setText(date_text)

        dialog.receipt_number.setText(payload.get("receipt_number") or "")
        dialog.payer_name.setText(payload.get("payer_name") or "")

        pm_text = payload.get("payment_method") or "نقداً"
        pm_idx = dialog.payment_method.findText(pm_text)
        if pm_idx >= 0:
            dialog.payment_method.setCurrentIndex(pm_idx)

        dialog.check_number.setText(payload.get("check_number") or "")
        dialog.bank_name.setText(payload.get("bank_name") or "")
        due_date = payload.get("due_date")
        if due_date:
            try:
                dialog.due_date.setText(due_date.strftime("%d/%m/%Y"))
            except Exception:
                pass
        dialog.reference_number.setText(payload.get("reference_number") or "")

        dist_mode = payload.get("distribution_mode") or "بالتساوي"
        dist_idx = dialog.division_mode_combo.findText(dist_mode)
        if dist_idx >= 0:
            dialog.division_mode_combo.setCurrentIndex(dist_idx)
        dialog.divide_checkbox.setChecked(bool(payload.get("should_distribute")))
        if hasattr(dialog, "include_guardian_checkbox"):
            dialog.include_guardian_checkbox.setChecked(bool(payload.get("include_guardian_share")))

        dialog.note.setText(payload.get("note") or "")

    def _calculate_financial_row_total(self, table: QTableWidget, row: int) -> float:
        total_cols = table.columnCount()
        total_col, _, _, _, entity_start_col = self._get_financial_table_special_columns(table)
        if total_cols < 5 or row < 2:
            return 0.0

        total_balance = 0.0
        for col_idx in range(entity_start_col, total_col):
            cell_item = table.item(row, col_idx)
            if cell_item and cell_item.text().strip():
                try:
                    value = float(cell_item.text().strip().replace(',', ''))
                    if (col_idx - entity_start_col) % 2 == 0:
                        total_balance += value
                    else:
                        total_balance -= value
                except ValueError:
                    pass
        return total_balance

    def _get_t_table_entity_column_map(self):
        """Return map: (kind, id) -> base column (deposit col) for t_table entities."""
        mapping = {}
        _, _, _, _, entity_start_col = self._get_financial_table_special_columns(self.t_table)
        col_idx = entity_start_col
        for entity in self.t_table_entities:
            mapping[(entity.get("kind"), entity.get("id"))] = col_idx
            col_idx += 2
        return mapping

    def _set_t_table_row_entity_editable(self, row: int, editable: bool):
        if row < 2:
            return

        total_col, _, _, _, entity_start_col = self._get_financial_table_special_columns(self.t_table)
        for col in range(entity_start_col, total_col):
            item = self.t_table.item(row, col)
            if not item:
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if (col - entity_start_col) % 2 == 0:
                    item.setBackground(QColor("#c8e6c9"))
                    item.setForeground(QColor("black"))
                else:
                    item.setBackground(QColor("#ffcdd2"))
                    item.setForeground(QColor("black"))
                self.t_table.setItem(row, col, item)

            flags = item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if editable:
                flags = flags | Qt.ItemFlag.ItemIsEditable
            else:
                flags = flags & ~Qt.ItemFlag.ItemIsEditable
            item.setFlags(flags)

    def _clear_t_table_row_entity_amounts(self, row: int):
        if row < 2:
            return

        total_col, _, _, _, entity_start_col = self._get_financial_table_special_columns(self.t_table)
        for col in range(entity_start_col, total_col):
            item = self.t_table.item(row, col)
            if not item:
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if (col - entity_start_col) % 2 == 0:
                    item.setBackground(QColor("#c8e6c9"))
                    item.setForeground(QColor("black"))
                else:
                    item.setBackground(QColor("#ffcdd2"))
                    item.setForeground(QColor("black"))
                self.t_table.setItem(row, col, item)
            item.setText("")

        self.recalculate_financial_row_balance(self.t_table, row)

    def _calculate_beneficiary_shares(self, beneficiaries, total_amount: Decimal, mode: str):
        return calculate_beneficiary_distribution(beneficiaries, total_amount, mode)

    def _apply_distribution_preview_to_t_table_row(self, row: int, payload: dict):
        """Populate row cells with distributed amounts (deposit columns) and note preview."""
        if row < 2 or not isinstance(payload, dict):
            return

        amount = to_decimal_money(payload.get("amount"))
        if amount <= 0:
            return

        include_guardian_share = bool(payload.get("include_guardian_share"))
        dist_mode = payload.get("distribution_mode") or "بالتساوي"

        beneficiaries = []
        for entity in getattr(self, "t_table_entities", []):
            if entity.get("kind") == "orphan":
                orphan_obj = next((o for o in getattr(self, "d_orphans", []) if o.id == entity.get("id")), None)
                beneficiaries.append({
                    "kind": "orphan",
                    "id": entity.get("id"),
                    "gender": orphan_obj.gender if orphan_obj else None,
                })

        if include_guardian_share and self.current_primary_guardian_for_t_table:
            beneficiaries.append({
                "kind": "guardian",
                "id": self.current_primary_guardian_for_t_table.id,
                "gender": None,
                "orphan_id": self.current_primary_guardian_orphan_id_for_t_table,
            })

        shares = self._calculate_beneficiary_shares(beneficiaries, amount, dist_mode)
        col_map = self._get_t_table_entity_column_map()

        # مهم: إعادة ضبط كل أعمدة الكيانات قبل تعبئة التوزيع الجديد
        # حتى لا تبقى قيم قديمة (مثلاً حصة الوصي) بعد تغيير إعدادات التوزيع.
        for base_col in col_map.values():
            dep_reset_item = self.t_table.item(row, base_col) or QTableWidgetItem("")
            dep_reset_item.setText("")
            dep_reset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dep_reset_item.setBackground(QColor("#c8e6c9"))
            dep_reset_item.setForeground(QColor("black"))
            self.t_table.setItem(row, base_col, dep_reset_item)

            wd_reset_item = self.t_table.item(row, base_col + 1) or QTableWidgetItem("")
            wd_reset_item.setText("")
            wd_reset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            wd_reset_item.setBackground(QColor("#ffcdd2"))
            wd_reset_item.setForeground(QColor("black"))
            self.t_table.setItem(row, base_col + 1, wd_reset_item)

        for key, share_amount in shares.items():
            base_col = col_map.get(key)
            if base_col is None:
                continue
            dep_item = self.t_table.item(row, base_col) or QTableWidgetItem("")
            dep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dep_item.setBackground(QColor("#c8e6c9"))
            dep_item.setForeground(QColor("black"))
            dep_item.setText(f"{Decimal(str(share_amount)):,.2f}")
            self.t_table.setItem(row, base_col, dep_item)

            wd_item = self.t_table.item(row, base_col + 1) or QTableWidgetItem("")
            wd_item.setText("")
            wd_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            wd_item.setBackground(QColor("#ffcdd2"))
            wd_item.setForeground(QColor("black"))
            self.t_table.setItem(row, base_col + 1, wd_item)

        total_col, note_col, _, _, _ = self._get_financial_table_special_columns(self.t_table)
        note_text = (payload.get("note") or "").strip()
        note_item = self.t_table.item(row, note_col) or QTableWidgetItem("")
        note_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        note_item.setText(note_text)
        self.t_table.setItem(row, note_col, note_item)

        # عند التوزيع، اقفل أعمدة الأيتام/الوصي لهذا الصف لمنع التعديل اليدوي
        self._set_t_table_row_entity_editable(row, editable=False)

        self.recalculate_financial_row_balance(self.t_table, row)

    def on_t_table_cell_double_clicked(self, row: int, col: int):
        if row < 2:
            return

        _, note_col, action_col, delete_col, _ = self._get_financial_table_special_columns(self.t_table)
        if col == delete_col:
            self._handle_t_table_row_delete(row)
            return
        if col != action_col:
            return

        if not self.current_deceased_for_t_table:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار متوفى أولاً.")
            return

        selected_currency_id = self.c_combo.currentData()
        selected_currency_code = None
        if selected_currency_id:
            selected_currency = self.db_service.session.query(Currency).get(selected_currency_id)
            selected_currency_code = selected_currency.code if selected_currency and selected_currency.code else None
        if not selected_currency_code:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار العملة من الحقل C_Combo أولاً.")
            return

        action_item = self.t_table.item(row, action_col)
        action_payload = action_item.data(Qt.ItemDataRole.UserRole) if action_item else None
        original_action_text = action_item.text() if action_item else ""
        original_action_payload = action_payload

        existing_txn_id = None
        distribution_anchor_txn_id = None
        prefill_payload = None
        was_distribution_before_edit = False
        if isinstance(action_payload, dict):
            status = action_payload.get("status")
            if status == "saved":
                existing_txn_id = action_payload.get("txn_id")
                distribution_anchor_txn_id = action_payload.get("distribution_anchor_txn_id")
            elif status == "pending":
                existing_txn_id = action_payload.get("target_txn_id")
                distribution_anchor_txn_id = action_payload.get("distribution_anchor_txn_id")
                prefill_payload = action_payload.get("payload") or None
                was_distribution_before_edit = bool((prefill_payload or {}).get("should_distribute"))

        row_total = self._calculate_financial_row_total(self.t_table, row)

        dialog = AddTransactionDialog(
            deceased_id=self.current_deceased_for_t_table.id,
            db_service=self.db_service,
            parent=self,
            forced_currency_code=selected_currency_code,
            hide_currency_field=True,
            hide_date_field=True,
        )

        has_pending_payload = bool(
            isinstance(action_payload, dict)
            and action_payload.get("status") == "pending"
            and isinstance(prefill_payload, dict)
        )

        if has_pending_payload:
            note_item = self.t_table.item(row, note_col)
            note_preview_text = note_item.text().strip() if note_item else ""
            if note_preview_text != str(prefill_payload.get("note") or "").strip():
                prefill_payload = dict(prefill_payload)
                prefill_payload["note"] = note_preview_text

            self._prefill_add_transaction_dialog(dialog, prefill_payload)

        elif existing_txn_id:
            existing_txn = self.db_service.session.query(DeceasedTransaction).filter_by(id=existing_txn_id).first()
            if not existing_txn:
                QMessageBox.warning(self, "تنبيه", "لم يتم العثور على الحركة المرتبطة بهذا الصف.")
                return

            if not prefill_payload:
                prefill_payload = self._build_deceased_payload_from_txn(existing_txn)

                linked_orphan_txns = self.db_service.session.query(Transaction).filter_by(
                    deceased_transaction_id=existing_txn.id
                ).all()

                distribution_anchor_txn = existing_txn if linked_orphan_txns else None

                if not linked_orphan_txns and existing_txn.type == TransactionTypeEnum.deposit:
                    candidate_withdraws = self.db_service.session.query(DeceasedTransaction).filter(
                        DeceasedTransaction.deceased_id == existing_txn.deceased_id,
                        DeceasedTransaction.currency_id == existing_txn.currency_id,
                        DeceasedTransaction.amount == existing_txn.amount,
                        DeceasedTransaction.type == TransactionTypeEnum.withdraw,
                        DeceasedTransaction.is_auto_manual_distribution == False,
                    ).order_by(DeceasedTransaction.id.desc()).limit(30).all()

                    existing_date_only = existing_txn.created_date.date() if existing_txn.created_date else None
                    for cand in candidate_withdraws:
                        cand_linked = self.db_service.session.query(Transaction).filter_by(
                            deceased_transaction_id=cand.id
                        ).all()
                        if not cand_linked:
                            continue

                        if existing_date_only and cand.created_date and cand.created_date.date() != existing_date_only:
                            continue

                        distribution_anchor_txn = cand
                        linked_orphan_txns = cand_linked
                        break

                if linked_orphan_txns and distribution_anchor_txn:
                    was_distribution_before_edit = True
                    note_text = (distribution_anchor_txn.note or existing_txn.note or "").strip()
                    inferred_mode = "للذكر مثل حظ الأنثيين" if "للذكر مثل حظ الأنثيين" in note_text else "بالتساوي"

                    # إن كانت الحركة المسجلة هي سحب ناتج عن (إيداع + توزيع)،
                    # نعرضها للمستخدم كإيداع + توزيع لتفادي التحقق الخاطئ من الرصيد.
                    if distribution_anchor_txn.type == TransactionTypeEnum.withdraw:
                        paired_deposit_txn = self.db_service.session.query(DeceasedTransaction).filter(
                            DeceasedTransaction.id != distribution_anchor_txn.id,
                            DeceasedTransaction.deceased_id == distribution_anchor_txn.deceased_id,
                            DeceasedTransaction.currency_id == distribution_anchor_txn.currency_id,
                            DeceasedTransaction.amount == distribution_anchor_txn.amount,
                            DeceasedTransaction.type == TransactionTypeEnum.deposit,
                        ).order_by(DeceasedTransaction.id.desc()).limit(30).all()

                        selected_deposit = None
                        anchor_date_only = distribution_anchor_txn.created_date.date() if distribution_anchor_txn.created_date else None
                        for dep in paired_deposit_txn:
                            if anchor_date_only and dep.created_date and dep.created_date.date() != anchor_date_only:
                                continue
                            selected_deposit = dep
                            break

                        if not selected_deposit and existing_txn.type == TransactionTypeEnum.deposit:
                            selected_deposit = existing_txn

                        if selected_deposit:
                            prefill_payload = self._build_deceased_payload_from_txn(selected_deposit)
                            prefill_payload["type"] = "deposit"
                        else:
                            prefill_payload["type"] = "withdraw"
                    else:
                        prefill_payload["type"] = "deposit"

                    prefill_payload["should_distribute"] = True
                    prefill_payload["distribution_mode"] = inferred_mode

                    include_guardian_share = False
                    if self.current_primary_guardian_for_t_table:
                        guardian_dist_txn = self.db_service.session.query(GuardianTransaction).filter(
                            GuardianTransaction.guardian_id == self.current_primary_guardian_for_t_table.id,
                            GuardianTransaction.deceased_id == distribution_anchor_txn.deceased_id,
                            or_(
                                GuardianTransaction.deceased_transaction_id == distribution_anchor_txn.id,
                                and_(
                                    GuardianTransaction.currency_id == distribution_anchor_txn.currency_id,
                                    GuardianTransaction.created_date == distribution_anchor_txn.created_date,
                                    GuardianTransaction.note.like("حصة وصي من توزيع%"),
                                )
                            ),
                        ).first()
                        include_guardian_share = bool(guardian_dist_txn)
                    prefill_payload["include_guardian_share"] = include_guardian_share

            self._prefill_add_transaction_dialog(dialog, prefill_payload)
        elif prefill_payload:
            self._prefill_add_transaction_dialog(dialog, prefill_payload)
        else:
            txn_type_text = "سحب" if row_total > 0 else "إيداع"
            type_idx = dialog.combo_type.findText(txn_type_text)
            if type_idx >= 0:
                dialog.combo_type.setCurrentIndex(type_idx)

            prefill_amount = min(abs(float(row_total)), 9_999_999.99)
            dialog.amount_input.setValue(prefill_amount)

            date_item = self.t_table.item(row, 1)
            date_text = date_item.text().strip() if date_item else ""
            if QDate.fromString(date_text, "dd/MM/yyyy").isValid():
                dialog.date_input.setText(date_text)

            note_item = self.t_table.item(row, note_col)
            if note_item and note_item.text().strip():
                dialog.note.setText(note_item.text().strip())

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_transaction_data()

            if existing_txn_id and isinstance(prefill_payload, dict):
                before = self._normalize_deceased_payload_for_compare(prefill_payload)
                after = self._normalize_deceased_payload_for_compare(new_data)
                if before == after:
                    if not action_item:
                        action_item = self._create_t_table_deceased_action_item()
                        self.t_table.setItem(row, action_col, action_item)
                    action_item.setText(original_action_text or f"تمت الإضافة #{existing_txn_id}")
                    action_item.setData(Qt.ItemDataRole.UserRole, original_action_payload)
                    return

            if not action_item:
                action_item = self._create_t_table_deceased_action_item()
                self.t_table.setItem(row, action_col, action_item)

            pending_payload = {
                "status": "pending",
                "payload": new_data,
            }
            if existing_txn_id:
                pending_payload["target_txn_id"] = existing_txn_id
                if distribution_anchor_txn_id:
                    pending_payload["distribution_anchor_txn_id"] = distribution_anchor_txn_id
                action_item.setText(f"تعديل معلّق #{existing_txn_id}")
            else:
                action_item.setText("جاهزة للحفظ")

            action_item.setData(Qt.ItemDataRole.UserRole, pending_payload)

            is_manual_mode = str(new_data.get("distribution_mode") or "").strip() == "يدوي"
            if new_data.get("should_distribute") and not is_manual_mode:
                self._apply_distribution_preview_to_t_table_row(row, new_data)
            else:
                self._set_t_table_row_entity_editable(row, editable=True)
                if was_distribution_before_edit:
                    self._clear_t_table_row_entity_amounts(row)
                _, note_col, _, _, _ = self._get_financial_table_special_columns(self.t_table)
                note_text = (new_data.get("note") or "").strip()
                note_item = self.t_table.item(row, note_col) or QTableWidgetItem("")
                note_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                note_item.setText(note_text)
                self.t_table.setItem(row, note_col, note_item)

            # QMessageBox.information(self, "تم", "تم ربط تفاصيل الحركة بهذا الصف ولن تُحفظ إلا عند الضغط على زر الحفظ.")

    def _handle_t_table_row_delete(self, row: int):
        if row < 2:
            return

        _, _, action_col, _, _ = self._get_financial_table_special_columns(self.t_table)
        action_item = self.t_table.item(row, action_col)
        action_payload = action_item.data(Qt.ItemDataRole.UserRole) if action_item else None

        id_item = self.t_table.item(row, 0)
        row_key = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None

        # صف غير محفوظ بعد: حذف من الجدول فقط
        if not row_key and (not isinstance(action_payload, dict) or action_payload.get("status") != "saved"):
            self.t_table.removeRow(row)
            return
        
        reply = QMessageBox.question(
            self,
            "تأكيد الحذف",
            "سيتم حذف كل الحركات الموجودة بالصف (حركة المتوفي وحركات الورثة). هل أنت متأكد؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db = self.db_service.session
        try:
            currency_id = self.c_combo.currentData()
            if not currency_id:
                raise ValueError("يرجى اختيار العملة أولاً.")

            row_created_at = None
            row_group_key = None
            if row_key:
                row_created_at = self._parse_row_datetime_key(row_key)
                if not row_created_at:
                    row_group_key = str(row_key).strip()

            def reverse_orphan_txn(txn):
                bal = db.query(OrphanBalance).filter_by(orphan_id=txn.orphan_id, currency_id=txn.currency_id).first()
                if not bal:
                    return
                amount = Decimal(str(txn.amount or 0))
                if txn.type == TransactionTypeEnum.deposit:
                    bal.balance = Decimal(str(bal.balance or 0)) - amount
                else:
                    bal.balance = Decimal(str(bal.balance or 0)) + amount

            def reverse_guardian_txn(txn):
                bal = db.query(GuardianBalance).filter_by(guardian_id=txn.guardian_id, currency_id=txn.currency_id).first()
                if not bal:
                    return
                amount = Decimal(str(txn.amount or 0))
                if txn.type == TransactionTypeEnum.deposit:
                    bal.balance = Decimal(str(bal.balance or 0)) - amount
                else:
                    bal.balance = Decimal(str(bal.balance or 0)) + amount

            def reverse_deceased_txn(txn):
                bal = db.query(DeceasedBalance).filter_by(deceased_id=txn.deceased_id, currency_id=txn.currency_id).first()
                if not bal:
                    return
                amount = Decimal(str(txn.amount or 0))
                if txn.type == TransactionTypeEnum.deposit:
                    bal.balance = Decimal(str(bal.balance or 0)) - amount
                else:
                    bal.balance = Decimal(str(bal.balance or 0)) + amount

            orphan_ids = [e.get("id") for e in getattr(self, "t_table_entities", []) if e.get("kind") == "orphan"]
            guardian_ids = [e.get("id") for e in getattr(self, "t_table_entities", []) if e.get("kind") == "guardian"]

            orphan_txns = []
            guardian_txns = []
            if row_group_key:
                orphan_txns = db.query(Transaction).filter(
                    Transaction.currency_id == currency_id,
                    Transaction.row_group_key == row_group_key,
                ).all()

                guardian_query = db.query(GuardianTransaction).filter(
                    GuardianTransaction.currency_id == currency_id,
                    GuardianTransaction.row_group_key == row_group_key,
                )
                if self.current_deceased_for_t_table:
                    guardian_query = guardian_query.filter(
                        GuardianTransaction.deceased_id == self.current_deceased_for_t_table.id
                    )
                guardian_txns = guardian_query.all()
            else:
                if not orphan_ids and self.current_deceased_for_t_table:
                    orphan_ids = [
                        orphan_id
                        for (orphan_id,) in db.query(Orphan.id).filter(
                            Orphan.deceased_id == self.current_deceased_for_t_table.id
                        ).all()
                    ]

                if orphan_ids:
                    orphan_query = db.query(Transaction).filter(
                        Transaction.orphan_id.in_(orphan_ids),
                        Transaction.currency_id == currency_id,
                    )
                    if row_created_at:
                        orphan_query = orphan_query.filter(Transaction.created_at == row_created_at)
                    orphan_txns = orphan_query.all()

                if guardian_ids:
                    guardian_query = db.query(GuardianTransaction).filter(
                        GuardianTransaction.guardian_id.in_(guardian_ids),
                        GuardianTransaction.deceased_id == self.current_deceased_for_t_table.id,
                        GuardianTransaction.currency_id == currency_id,
                    )
                    if row_created_at:
                        guardian_query = guardian_query.filter(GuardianTransaction.created_at == row_created_at)
                    guardian_txns = guardian_query.all()

            if not row_created_at:
                sample_txn = (orphan_txns[0] if orphan_txns else (guardian_txns[0] if guardian_txns else None))
                if sample_txn:
                    row_created_at = getattr(sample_txn, "created_at", None) or getattr(sample_txn, "created_date", None)

            for txn in orphan_txns:
                reverse_orphan_txn(txn)
                db.delete(txn)

            for txn in guardian_txns:
                reverse_guardian_txn(txn)
                db.delete(txn)

            deceased_ids = set()
            for txn in orphan_txns:
                linked_id = getattr(txn, "deceased_transaction_id", None)
                if linked_id:
                    deceased_ids.add(linked_id)

            for txn in guardian_txns:
                linked_id = getattr(txn, "deceased_transaction_id", None)
                if linked_id:
                    deceased_ids.add(linked_id)

            if isinstance(action_payload, dict):
                for key in ("distribution_anchor_txn_id", "txn_id", "target_txn_id"):
                    tx_id = action_payload.get(key)
                    if tx_id:
                        deceased_ids.add(tx_id)

            # دعم إضافي لاكتشاف حركة المتوفى حسب الصف عند غياب المعرّف في الـ payload
            if row_group_key and self.current_deceased_for_t_table:
                grouped_deceased_txns = db.query(DeceasedTransaction).filter(
                    DeceasedTransaction.deceased_id == self.current_deceased_for_t_table.id,
                    DeceasedTransaction.currency_id == currency_id,
                    DeceasedTransaction.row_group_key == row_group_key,
                ).all()
                for txn in grouped_deceased_txns:
                    deceased_ids.add(txn.id)

            if row_created_at and self.current_deceased_for_t_table:
                fallback_txns = db.query(DeceasedTransaction).filter(
                    DeceasedTransaction.deceased_id == self.current_deceased_for_t_table.id,
                    DeceasedTransaction.currency_id == currency_id,
                    DeceasedTransaction.created_date == row_created_at,
                ).all()
                for txn in fallback_txns:
                    deceased_ids.add(txn.id)

            deceased_txns_to_delete = {}
            for tx_id in deceased_ids:
                txn = db.query(DeceasedTransaction).filter_by(id=tx_id).first()
                if not txn:
                    continue
                deceased_txns_to_delete[txn.id] = txn

                if txn.type == TransactionTypeEnum.withdraw:
                    pair = db.query(DeceasedTransaction).filter(
                        DeceasedTransaction.id != txn.id,
                        DeceasedTransaction.deceased_id == txn.deceased_id,
                        DeceasedTransaction.currency_id == txn.currency_id,
                        DeceasedTransaction.amount == txn.amount,
                        DeceasedTransaction.type == TransactionTypeEnum.deposit,
                        DeceasedTransaction.created_date == txn.created_date,
                    ).order_by(DeceasedTransaction.id.desc()).first()
                    if pair:
                        deceased_txns_to_delete[pair.id] = pair

            for txn in deceased_txns_to_delete.values():
                reverse_deceased_txn(txn)
                db.delete(txn)

            db.commit()
            self.t_table.removeRow(row)
            self._refresh_financial_entity_header_balances(self.t_table)
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر حذف حركات الصف: {e}")
            return

    def recalculate_financial_row_balance(self, table: QTableWidget, row: int):
        if row < 2:
            return

        total_cols = table.columnCount()
        total_col, _, _, _, _ = self._get_financial_table_special_columns(table)

        try:
            total_balance = self._calculate_financial_row_total(table, row)

            balance_cell = table.item(row, total_col)
            if not balance_cell:
                balance_cell = QTableWidgetItem()
                balance_cell.setFlags(balance_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, total_col, balance_cell)
            balance_cell.setText(f"{total_balance:,.2f}")
            self._refresh_financial_entity_header_balances(table)
        except Exception as e:
            print(f"خطأ في حساب الرصيد: {e}")

    def _refresh_financial_entity_header_balances(self, table: QTableWidget):
        if not table or table.columnCount() < 6 or table.rowCount() < 2:
            return

        _, _, _, _, entity_start_col = self._get_financial_table_special_columns(table)
        entities = getattr(self, "t_table_entities", []) or []
        if not entities:
            return

        with QSignalBlocker(table):
            col_idx = entity_start_col
            for entity in entities:
                if col_idx + 1 >= table.columnCount():
                    break

                total_balance = 0.0
                for row in range(2, table.rowCount()):
                    dep_item = table.item(row, col_idx)
                    wd_item = table.item(row, col_idx + 1)

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

                    total_balance += dep_val - wd_val

                header_item = table.item(0, col_idx)
                if not header_item:
                    header_item = QTableWidgetItem()
                    table.setItem(0, col_idx, header_item)

                header_title = (entity.get("header_title") or entity.get("name") or "").strip()
                header_item.setText(f"{header_title}\nالرصيد: {total_balance:,.2f}")
                header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                col_idx += 2

    def _enable_excel_like_table(self, table: QTableWidget, header_rows: int = 0):
        table.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.AnyKeyPressed |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        table.setTabKeyNavigation(True)
        table.setAlternatingRowColors(True)

        key = table.objectName() or str(id(table))
        if key in self._excel_shortcuts_registry:
            return

        sc_copy = QShortcut(QKeySequence.StandardKey.Copy, table)
        sc_copy.activated.connect(lambda t=table, h=header_rows: self._copy_table_selection_to_clipboard(t, h))

        sc_paste = QShortcut(QKeySequence.StandardKey.Paste, table)
        sc_paste.activated.connect(lambda t=table, h=header_rows: self._paste_clipboard_into_table(t, h))

        sc_delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), table)
        sc_delete.activated.connect(lambda t=table, h=header_rows: self._clear_selected_cells(t, h))

        self._excel_shortcuts_registry[key] = [sc_copy, sc_paste, sc_delete]

    def _setup_t_table_column_width_controls(self):
        self.t_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.t_table.customContextMenuRequested.connect(self._show_t_table_column_menu)

        inc_shortcut_a = QShortcut(QKeySequence("Ctrl++"), self.t_table)
        inc_shortcut_b = QShortcut(QKeySequence("Ctrl+="), self.t_table)
        dec_shortcut = QShortcut(QKeySequence("Ctrl+-"), self.t_table)
        reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self.t_table)

        inc_shortcut_a.activated.connect(lambda: self._adjust_t_table_selected_columns(12))
        inc_shortcut_b.activated.connect(lambda: self._adjust_t_table_selected_columns(12))
        dec_shortcut.activated.connect(lambda: self._adjust_t_table_selected_columns(-12))
        reset_shortcut.activated.connect(self._reset_t_table_selected_columns_to_default)

        self._t_table_width_shortcuts = [inc_shortcut_a, inc_shortcut_b, dec_shortcut, reset_shortcut]

    def _get_t_table_selected_columns(self):
        selected_cols = sorted({idx.column() for idx in self.t_table.selectedIndexes()})
        if selected_cols:
            return selected_cols

        current_col = self.t_table.currentColumn()
        if current_col >= 0:
            return [current_col]
        return []

    def _adjust_t_table_selected_columns(self, delta: int):
        columns = self._get_t_table_selected_columns()
        if not columns:
            return

        min_width = 55
        max_width = 420
        for col in columns:
            current_width = self.t_table.columnWidth(col)
            new_width = max(min_width, min(max_width, current_width + delta))
            self.t_table.setColumnWidth(col, new_width)

    def _reset_t_table_selected_columns_to_default(self):
        columns = self._get_t_table_selected_columns()
        if not columns or not self._t_table_default_column_widths:
            return

        for col in columns:
            default_width = self._t_table_default_column_widths.get(col)
            if default_width:
                self.t_table.setColumnWidth(col, default_width)

    def _show_t_table_column_menu(self, position):
        if self.t_table.columnCount() == 0:
            return

        clicked_col = self.t_table.columnAt(position.x())
        if clicked_col >= 0:
            current_row = self.t_table.currentRow()
            if current_row < 0:
                current_row = 2 if self.t_table.rowCount() > 2 else 0
            self.t_table.setCurrentCell(current_row, clicked_col)

        menu = QMenu(self)
        expand_action = menu.addAction("توسيع عرض العمود المحدد")
        shrink_action = menu.addAction("تضييق عرض العمود المحدد")
        reset_action = menu.addAction("إعادة العرض الافتراضي للعمود")

        chosen = menu.exec(self.t_table.viewport().mapToGlobal(position))
        if chosen == expand_action:
            self._adjust_t_table_selected_columns(12)
        elif chosen == shrink_action:
            self._adjust_t_table_selected_columns(-12)
        elif chosen == reset_action:
            self._reset_t_table_selected_columns_to_default()

    def _get_table_cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        widget = table.cellWidget(row, col)
        if widget and isinstance(widget, QComboBox):
            return widget.currentText().strip()
        item = table.item(row, col)
        return item.text() if item else ""

    def _copy_table_selection_to_clipboard(self, table: QTableWidget, header_rows: int = 0):
        indexes = table.selectedIndexes()
        if not indexes:
            return

        valid_indexes = [idx for idx in indexes if idx.row() >= header_rows]
        if not valid_indexes:
            return

        min_row = min(idx.row() for idx in valid_indexes)
        max_row = max(idx.row() for idx in valid_indexes)
        min_col = min(idx.column() for idx in valid_indexes)
        max_col = max(idx.column() for idx in valid_indexes)

        selected = {(idx.row(), idx.column()) for idx in valid_indexes}
        lines = []
        for row in range(min_row, max_row + 1):
            values = []
            for col in range(min_col, max_col + 1):
                if (row, col) in selected:
                    values.append(self._get_table_cell_text(table, row, col))
                else:
                    values.append("")
            lines.append("\t".join(values))

        QApplication.clipboard().setText("\n".join(lines))

    def _initialize_financial_table_row(self, table: QTableWidget, row_position: int):
        total_cols = table.columnCount()
        total_col, note_col, action_col, delete_col, entity_start_col = self._get_financial_table_special_columns(table)

        id_item = QTableWidgetItem("")
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_position, 0, id_item)

        date_item = QTableWidgetItem("")
        date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_position, 1, date_item)

        for col_idx in range(entity_start_col, total_col):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if (col_idx - entity_start_col) % 2 == 0:
                item.setBackground(QColor("#c8e6c9"))
                item.setForeground(QColor("black"))
            else:
                item.setBackground(QColor("#ffcdd2"))
                item.setForeground(QColor("black"))
            table.setItem(row_position, col_idx, item)

        table.setItem(row_position, action_col, self._create_t_table_deceased_action_item())

        balance_item = QTableWidgetItem("0.00")
        balance_item.setFlags(balance_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        balance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        balance_item.setBackground(QColor("#f9f9f9"))
        table.setItem(row_position, total_col, balance_item)

        note_item = QTableWidgetItem("")
        note_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_position, note_col, note_item)
        table.setItem(row_position, delete_col, self._create_t_table_delete_item())

        if table is self.t_table:
            self._set_t_table_row_entity_editable(row_position, editable=True)

    def _paste_clipboard_into_table(self, table: QTableWidget, header_rows: int = 0):
        text = QApplication.clipboard().text()
        if not text:
            return

        start_row = table.currentRow()
        start_col = table.currentColumn()
        if start_row < header_rows:
            start_row = header_rows
        if start_row < 0:
            start_row = header_rows
        if start_col < 0:
            start_col = 0

        rows_data = [line.split('\t') for line in text.replace('\r\n', '\n').split('\n') if line != ""]
        if not rows_data:
            return

        affected_rows = set()
        for r_offset, values in enumerate(rows_data):
            target_row = start_row + r_offset
            while target_row >= table.rowCount():
                table.insertRow(table.rowCount())
                self._initialize_financial_table_row(table, table.rowCount() - 1)

            for c_offset, raw_value in enumerate(values):
                target_col = start_col + c_offset
                if target_col >= table.columnCount():
                    continue
                if target_row < header_rows:
                    continue

                current_item = table.item(target_row, target_col)
                if current_item and not (current_item.flags() & Qt.ItemFlag.ItemIsEditable):
                    continue

                if not current_item:
                    current_item = QTableWidgetItem("")
                    table.setItem(target_row, target_col, current_item)

                current_item.setText(raw_value)
                affected_rows.add(target_row)

        for row in affected_rows:
            self.recalculate_financial_row_balance(table, row)

    def _clear_selected_cells(self, table: QTableWidget, header_rows: int = 0):
        indexes = table.selectedIndexes()
        if not indexes:
            return

        affected_rows = set()
        for idx in indexes:
            row, col = idx.row(), idx.column()
            if row < header_rows:
                continue
            item = table.item(row, col)
            if not item:
                continue
            if not (item.flags() & Qt.ItemFlag.ItemIsEditable):
                continue
            item.setText("")
            affected_rows.add(row)

        for row in affected_rows:
            self.recalculate_financial_row_balance(table, row)

    def _copy_table_with_spans(self, source: QTableWidget, target: QTableWidget):
        target.clear()
        target.clearSpans()
        target.setRowCount(source.rowCount())
        target.setColumnCount(source.columnCount())

        for col in range(source.columnCount()):
            src_header = source.horizontalHeaderItem(col)
            if src_header:
                target.setHorizontalHeaderItem(col, src_header.clone())
            target.setColumnWidth(col, source.columnWidth(col))
            target.setColumnHidden(col, source.isColumnHidden(col))

        for row in range(source.rowCount()):
            target.setRowHeight(row, source.rowHeight(row))

        for row in range(source.rowCount()):
            for col in range(source.columnCount()):
                item = source.item(row, col)
                if item:
                    target.setItem(row, col, item.clone())

        visited = set()
        for row in range(source.rowCount()):
            for col in range(source.columnCount()):
                if (row, col) in visited:
                    continue
                r_span = source.rowSpan(row, col)
                c_span = source.columnSpan(row, col)
                if r_span > 1 or c_span > 1:
                    target.setSpan(row, col, r_span, c_span)
                    for rr in range(row, row + r_span):
                        for cc in range(col, col + c_span):
                            visited.add((rr, cc))

        target.horizontalHeader().setVisible(source.horizontalHeader().isVisible())
        target.verticalHeader().setVisible(source.verticalHeader().isVisible())
        target.setWordWrap(source.wordWrap())
        target.setTextElideMode(source.textElideMode())
        target.setStyleSheet(source.styleSheet())

    def open_t_table_fullscreen_editor(self):
        if self.t_table.columnCount() == 0:
            QMessageBox.warning(self, "تنبيه", "لا يوجد جدول مفتوح حالياً لعرضه.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("إدخال الحركات - شاشة كاملة")
        dialog.setWindowFlag(Qt.WindowType.Window, True)
        dialog.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        dialog.setWindowState(Qt.WindowState.WindowMaximized)

        layout = QVBoxLayout(dialog)

        def resolve_icon(paths, fallback_icon: QStyle.StandardPixmap):
            for rel_path in paths:
                abs_path = resource_path(rel_path)
                if os.path.exists(abs_path):
                    return QIcon(abs_path)
            return dialog.style().standardIcon(fallback_icon)

        toolbar_layout = QHBoxLayout()
        add_row_btn = QPushButton("إضافة صف")
        add_row_with_dialog_btn = QPushButton("نموذج حركة جديدة")
        remove_row_btn = QPushButton("حذف صف")
        save_btn = QPushButton("حفظ التعديلات")
        cancel_btn = QPushButton("إلغاء")

        add_row_btn.setIcon(resolve_icon([
            os.path.join("assets", "images", "plus_1.png"),
            os.path.join("assets", "images", "plus.png"),
        ], QStyle.StandardPixmap.SP_FileDialogNewFolder))
        add_row_with_dialog_btn.setIcon(resolve_icon([
            os.path.join("assets", "icons", "ic_fluent_form_new_24_filled_white.svg"),
            # os.path.join("assets", "icons", "ic_fluent_form_new_24_filled_white.svg"),
        ], QStyle.StandardPixmap.SP_FileDialogDetailedView))
        remove_row_btn.setIcon(resolve_icon([
            os.path.join("assets", "images", "minus_white.png"),
            os.path.join("assets", "images", "minus.png"),
        ], QStyle.StandardPixmap.SP_TrashIcon))

        toolbar_layout.addWidget(add_row_btn)
        toolbar_layout.addWidget(remove_row_btn)
        toolbar_layout.addWidget(add_row_with_dialog_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(save_btn)
        toolbar_layout.addWidget(cancel_btn)
        layout.addLayout(toolbar_layout)

        table_editor = QTableWidget(dialog)
        layout.addWidget(table_editor)
        self._copy_table_with_spans(self.t_table, table_editor)
        self._enable_excel_like_table(table_editor, header_rows=2)
        table_editor.horizontalHeader().setStretchLastSection(True)

        def on_editor_cell_double_clicked(row: int, col: int):
            # Reuse the same business logic used by the main table for action/delete cells.
            # We sync editor -> main before handling, then main -> editor after handling.
            if row < 2:
                return
            try:
                _, _, action_col, delete_col, _ = self._get_financial_table_special_columns(table_editor)
            except Exception:
                return
            if col not in (action_col, delete_col):
                return

            self._copy_table_with_spans(table_editor, self.t_table)
            self.on_t_table_cell_double_clicked(row, col)
            self._copy_table_with_spans(self.t_table, table_editor)
            self._refresh_financial_entity_header_balances(table_editor)

        table_editor.cellDoubleClicked.connect(on_editor_cell_double_clicked)

        editor_default_column_widths = {
            c: table_editor.columnWidth(c) for c in range(table_editor.columnCount())
        }

        def get_selected_editor_columns():
            selected_cols = sorted({idx.column() for idx in table_editor.selectedIndexes()})
            if selected_cols:
                return selected_cols

            current_col = table_editor.currentColumn()
            if current_col >= 0:
                return [current_col]
            return []

        def adjust_editor_columns(delta: int):
            columns = get_selected_editor_columns()
            if not columns:
                return

            min_width = 55
            max_width = 420
            for col in columns:
                current_width = table_editor.columnWidth(col)
                new_width = max(min_width, min(max_width, current_width + delta))
                table_editor.setColumnWidth(col, new_width)

        def reset_editor_columns_to_default():
            columns = get_selected_editor_columns()
            if not columns:
                return

            for col in columns:
                default_width = editor_default_column_widths.get(col)
                if default_width:
                    table_editor.setColumnWidth(col, default_width)

        def show_editor_column_menu(position):
            if table_editor.columnCount() == 0:
                return

            clicked_col = table_editor.columnAt(position.x())
            if clicked_col >= 0:
                current_row = table_editor.currentRow()
                if current_row < 0:
                    current_row = 2 if table_editor.rowCount() > 2 else 0
                table_editor.setCurrentCell(current_row, clicked_col)

            menu = QMenu(dialog)
            expand_action = menu.addAction("توسيع عرض العمود المحدد")
            shrink_action = menu.addAction("تضييق عرض العمود المحدد")
            reset_action = menu.addAction("إعادة العرض الافتراضي للعمود")

            chosen = menu.exec(table_editor.viewport().mapToGlobal(position))
            if chosen == expand_action:
                adjust_editor_columns(12)
            elif chosen == shrink_action:
                adjust_editor_columns(-12)
            elif chosen == reset_action:
                reset_editor_columns_to_default()

        table_editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table_editor.customContextMenuRequested.connect(show_editor_column_menu)

        inc_shortcut_a = QShortcut(QKeySequence("Ctrl++"), table_editor)
        inc_shortcut_b = QShortcut(QKeySequence("Ctrl+="), table_editor)
        dec_shortcut = QShortcut(QKeySequence("Ctrl+-"), table_editor)
        reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), table_editor)

        inc_shortcut_a.activated.connect(lambda: adjust_editor_columns(12))
        inc_shortcut_b.activated.connect(lambda: adjust_editor_columns(12))
        dec_shortcut.activated.connect(lambda: adjust_editor_columns(-12))
        reset_shortcut.activated.connect(reset_editor_columns_to_default)

        editor_width_shortcuts = [inc_shortcut_a, inc_shortcut_b, dec_shortcut, reset_shortcut]

        def on_editor_item_changed(changed_item):
            self.recalculate_financial_row_balance(table_editor, changed_item.row())

        table_editor.itemChanged.connect(on_editor_item_changed)

        def add_editor_row():
            row_position = table_editor.rowCount()
            table_editor.insertRow(row_position)
            self._initialize_financial_table_row(table_editor, row_position)
            table_editor.setCurrentCell(row_position, 1)

        def add_editor_row_with_dialog():
            if table_editor.columnCount() == 0:
                QMessageBox.warning(dialog, "تنبيه", "يرجى اختيار متوفى أولاً لتجهيز جدول المعاملات.")
                return

            add_dialog = AddTTableRowDialog(parent=self)
            if not add_dialog.exec():
                return

            row_data = add_dialog.get_data() or {}

            # حفظ مباشر بنفس منطق النافذة الأساسية ثم مزامنة الجدول الكبير فوراً.
            self.save_t_table_dialog_row_directly(row_data)
            self._copy_table_with_spans(self.t_table, table_editor)
            self._refresh_financial_entity_header_balances(table_editor)

            last_row = table_editor.rowCount() - 1
            if last_row >= 2:
                table_editor.setCurrentCell(last_row, 1)

        def remove_editor_row():
            row = table_editor.currentRow()
            if row == -1:
                QMessageBox.warning(dialog, "تنبيه", "يرجى تحديد الصف المراد حذفه أولاً.")
                return
            if row < 2:
                return

            id_item = table_editor.item(row, 0)
            if id_item and id_item.text().strip():
                return

            table_editor.removeRow(row)
            self._refresh_financial_entity_header_balances(table_editor)

        add_row_btn.clicked.connect(add_editor_row)
        add_row_with_dialog_btn.clicked.connect(add_editor_row_with_dialog)
        remove_row_btn.clicked.connect(remove_editor_row)

        def apply_and_close():
            self._copy_table_with_spans(table_editor, self.t_table)
            try:
                self.t_table.itemChanged.disconnect(self.on_t_table_cell_changed)
            except Exception:
                pass
            self.t_table.itemChanged.connect(self.on_t_table_cell_changed)
            self._refresh_financial_entity_header_balances(self.t_table)
            self.update_t_table_buttons_state()
            dialog.accept()

        save_btn.clicked.connect(apply_and_close)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()
    
    def get_table_data_on_save(self):
        currency_id = self.c_combo.currentData()
        all_data = [
            {"currency_id": currency_id},
        ]
        total_col, note_col, action_col, _, entity_start_col = self._get_financial_table_special_columns(self.t_table)

        def parse_decimal_cell(value):
            text = (value or "").strip().replace(',', '')
            if not text:
                return Decimal('0')
            try:
                return Decimal(text)
            except Exception:
                return Decimal('0')

        # نبدأ من الصف 2 لأن 0 و 1 هما العناوين
        for row in range(2, self.t_table.rowCount()):
            id_item = self.t_table.item(row, 0)
            row_data = {
                "_table_row": row + 1,
                "id": id_item.text() if id_item else None,
                "row_key": id_item.data(Qt.ItemDataRole.UserRole) if id_item else None,
                "date": self.t_table.item(row, 1).text() if self.t_table.item(row, 1) else "",
                "orphans_transactions": [],
                "guardian_transactions": [],
                "total_balance": self.t_table.item(row, total_col).text() if self.t_table.item(row, total_col) else "0",
                "note": self.t_table.item(row, note_col).text() if self.t_table.item(row, note_col) else "",
                "deceased_action": self.t_table.item(row, action_col).data(Qt.ItemDataRole.UserRole) if self.t_table.item(row, action_col) else None,
            }

            # استخراج بيانات الكيانات (الأيتام + الوصي الأساسي)
            col_idx = entity_start_col
            entities = getattr(self, "t_table_entities", [])
            for entity in entities:
                deposit = self.t_table.item(row, col_idx).text() if self.t_table.item(row, col_idx) else "0"
                withdraw = self.t_table.item(row, col_idx + 1).text() if self.t_table.item(row, col_idx + 1) else "0"

                payload = {
                    "deposit": parse_decimal_cell(deposit),
                    "withdraw": parse_decimal_cell(withdraw),
                }

                if entity["kind"] == "orphan":
                    row_data["orphans_transactions"].append({
                        "orphan_id": entity["id"],
                        "orphan_name": entity["name"],
                        **payload,
                    })
                else:
                    row_data["guardian_transactions"].append({
                        "guardian_id": entity["id"],
                        "guardian_name": entity["name"],
                        **payload,
                    })

                col_idx += 2 # الانتقال لليتيم التالي
                
            all_data.append(row_data)
        
        return all_data

    def _parse_dialog_due_date(self, due_date_text):
        """Convert dd/MM/yyyy text from AddTTableRowDialog to python date for DB storage."""
        raw_text = str(due_date_text or "").strip()
        if not raw_text:
            return None

        q_date = QDate.fromString(raw_text, "dd/MM/yyyy")
        if q_date.isValid():
            return q_date.toPyDate()
        return None

    def _build_direct_save_payload_from_t_table_dialog(self, row_data):
        """Map AddTTableRowDialog output to the same structure expected by save_transactions."""
        currency_id = self.c_combo.currentData()
        deceased_id = self.current_deceased_for_t_table.id if self.current_deceased_for_t_table else None

        has_deceased_action = bool(row_data.get("type")) and Decimal(str(row_data.get("amount") or 0)) > 0
        deceased_action_payload = None
        if has_deceased_action:
            deceased_action_payload = {
                "status": "pending",
                "payload": {
                    "deceased_id": deceased_id,
                    "currency_id": currency_id,
                    "amount": Decimal(str(row_data.get("amount") or 0)),
                    "type": row_data.get("type"),
                    "receipt_number": (row_data.get("receipt_number") or "").strip(),
                    "payer_name": (row_data.get("payer_name") or "").strip(),
                    "payment_method": row_data.get("payment_method"),
                    "check_number": (row_data.get("check_number") or "").strip() or None,
                    "due_date": self._parse_dialog_due_date(row_data.get("due_date")),
                    "bank_name": (row_data.get("bank_name") or "").strip() or None,
                    "reference_number": (row_data.get("reference_number") or "").strip() or None,
                    "should_distribute": bool(row_data.get("should_distribute")),
                    "distribution_mode": row_data.get("distribution_mode") or "يدوي",
                    "include_guardian_share": bool(row_data.get("include_guardian_share")),
                    "note": (row_data.get("note") or "").strip(),
                },
            }

        return [
            {"currency_id": currency_id},
            {
                "_table_row": 0,
                "id": None,
                "row_key": None,
                "date": (row_data.get("date_text") or "").strip(),
                "orphans_transactions": row_data.get("orphans_transactions", []),
                "guardian_transactions": row_data.get("guardian_transactions", []),
                "total_balance": "0",
                "note": (row_data.get("note") or "").strip(),
                "deceased_action": deceased_action_payload,
            },
        ]
    
    def save_transactions(self, data_override=None, success_message="تم حفظ البيانات بنجاح."):
        # توافق مع إشارات Qt (clicked) التي تمرر قيمة bool تلقائياً.
        if isinstance(data_override, bool):
            data_override = None

        data = data_override if data_override is not None else self.get_table_data_on_save()
        if not data or len(data) <= 1:  # لا توجد بيانات سوى العملة
            QMessageBox.warning(self, "تنبيه", "لا توجد بيانات للحفظ.")
            return
        
        try:
            db = self.db_service.session
            currency_id = data.pop(0)["currency_id"]  # استخراج معرف العملة من أول عنصر
            if not currency_id:
                raise ValueError("يرجى اختيار العملة قبل الحفظ")

            balance_cache = {}

            def get_balance_record(kind, person_id):
                if kind == "orphan":
                    return db.query(OrphanBalance).filter_by(
                        orphan_id=person_id,
                        currency_id=currency_id,
                    ).first()
                return db.query(GuardianBalance).filter_by(
                    guardian_id=person_id,
                    currency_id=currency_id,
                ).first()

            def get_available_balance(kind, person_id):
                key = (kind, person_id)
                if key in balance_cache:
                    return balance_cache[key]

                bal = get_balance_record(kind, person_id)

                balance_cache[key] = Decimal(str(bal.balance)) if bal else Decimal('0')
                return balance_cache[key]

            def apply_balance_delta(kind, person_id, delta: Decimal):
                current = get_available_balance(kind, person_id)
                new_balance = current + delta
                bal_rec = get_balance_record(kind, person_id)

                if bal_rec:
                    bal_rec.balance = new_balance
                else:
                    if kind == "orphan":
                        db.add(OrphanBalance(
                            orphan_id=person_id,
                            currency_id=currency_id,
                            balance=new_balance,
                        ))
                    else:
                        db.add(GuardianBalance(
                            guardian_id=person_id,
                            currency_id=currency_id,
                            balance=new_balance,
                        ))

                balance_cache[(kind, person_id)] = new_balance

            def update_deceased_balance(deceased_id, local_currency_id, amount: Decimal, txn_type: str):
                deceased_bal = db.query(DeceasedBalance).filter_by(
                    deceased_id=deceased_id,
                    currency_id=local_currency_id,
                ).first()
                is_deposit = (txn_type == "deposit")
                delta = amount if is_deposit else -amount
                if deceased_bal:
                    deceased_bal.balance = Decimal(str(deceased_bal.balance or 0)) + delta
                else:
                    db.add(DeceasedBalance(
                        deceased_id=deceased_id,
                        currency_id=local_currency_id,
                        balance=delta,
                    ))

            def update_orphan_balance(orphan_id, local_currency_id, amount: Decimal):
                orphan_bal = db.query(OrphanBalance).filter_by(
                    orphan_id=orphan_id,
                    currency_id=local_currency_id,
                ).first()
                if orphan_bal:
                    orphan_bal.balance = Decimal(str(orphan_bal.balance or 0)) + amount
                else:
                    db.add(OrphanBalance(
                        orphan_id=orphan_id,
                        currency_id=local_currency_id,
                        balance=amount,
                    ))

            def get_primary_guardian_for_deceased(local_deceased_id):
                primary_link = db.query(OrphanGuardian).join(
                    Orphan, Orphan.id == OrphanGuardian.orphan_id
                ).filter(
                    Orphan.deceased_id == local_deceased_id,
                    OrphanGuardian.is_primary == True,
                ).first()
                if primary_link:
                    return primary_link.guardian

                any_link = db.query(OrphanGuardian).join(
                    Orphan, Orphan.id == OrphanGuardian.orphan_id
                ).filter(
                    Orphan.deceased_id == local_deceased_id,
                ).first()
                return any_link.guardian if any_link else None

            def get_primary_guardian_link_for_deceased(local_deceased_id):
                primary_link = db.query(OrphanGuardian).join(
                    Orphan, Orphan.id == OrphanGuardian.orphan_id
                ).filter(
                    Orphan.deceased_id == local_deceased_id,
                    OrphanGuardian.is_primary == True,
                ).first()
                if primary_link:
                    return primary_link

                return db.query(OrphanGuardian).join(
                    Orphan, Orphan.id == OrphanGuardian.orphan_id
                ).filter(
                    Orphan.deceased_id == local_deceased_id,
                ).first()

            def calculate_shares(beneficiaries, total_amount: Decimal, mode: str):
                return self._calculate_beneficiary_shares(beneficiaries, total_amount, mode)

            def build_distribution_note(base_note, beneficiaries, shares, mode: str):
                base = (base_note or "").strip()
                chunks = []
                for beneficiary in beneficiaries:
                    key = (beneficiary.get("kind"), beneficiary.get("id"))
                    share_amount = Decimal(str(shares.get(key, 0)))
                    if share_amount <= 0:
                        continue

                    if beneficiary.get("kind") == "guardian":
                        label = f"الوصي {beneficiary.get('name') or ''}".strip()
                    else:
                        label = beneficiary.get("name") or f"يتيم {beneficiary.get('id')}"
                    chunks.append(f"{label}: {share_amount:,.2f}")

                details = f"تفاصيل التوزيع ({mode}): "
                details += "، ".join(chunks) if chunks else "لا توجد حصص"
                note_text = f"{base} | {details}" if base else details
                return note_text[:250]

            def create_deceased_txn_from_pending(action_payload, effective_created_date, default_note="", row_group_key=None):
                if not isinstance(action_payload, dict):
                    return None
                if action_payload.get("status") != "pending":
                    return None

                payload = action_payload.get("payload") or {}
                target_txn_id = action_payload.get("target_txn_id")
                distribution_anchor_txn_id = action_payload.get("distribution_anchor_txn_id")
                deceased_id = payload.get("deceased_id") or (self.current_deceased_for_t_table.id if self.current_deceased_for_t_table else None)
                local_currency_id = payload.get("currency_id") or currency_id
                amount = Decimal(str(payload.get("amount") or 0))
                txn_type = payload.get("type")
                is_manual_mode = is_manual_distribution_mode(payload.get("distribution_mode"))
                if not deceased_id or not local_currency_id or amount <= 0 or txn_type not in ("deposit", "withdraw"):
                    raise ValueError("بيانات حركة المتوفى غير مكتملة في أحد الصفوف.")

                if target_txn_id:
                    existing_txn = db.query(DeceasedTransaction).filter_by(id=target_txn_id).first()
                    if not existing_txn:
                        raise ValueError("تعذر العثور على الحركة المسجلة المطلوب تعديلها.")

                    # تثبيت معرف الحركة المعروضة للمستخدم عند التعديل
                    # حتى لا يتغير رقم الـ ID بعد الحفظ.
                    stable_display_txn_id = existing_txn.id

                    anchor_txn = existing_txn
                    if distribution_anchor_txn_id:
                        anchor_candidate = db.query(DeceasedTransaction).filter_by(id=distribution_anchor_txn_id).first()
                        if anchor_candidate:
                            anchor_txn = anchor_candidate

                    linked_orphan_txns = db.query(Transaction).filter_by(
                        deceased_transaction_id=anchor_txn.id
                    ).all()

                    is_old_distribution = bool(linked_orphan_txns)

                    paired_deposit_txn = None
                    if anchor_txn.type == TransactionTypeEnum.withdraw:
                        paired_deposit_txn = db.query(DeceasedTransaction).filter(
                            DeceasedTransaction.id != anchor_txn.id,
                            DeceasedTransaction.deceased_id == anchor_txn.deceased_id,
                            DeceasedTransaction.currency_id == anchor_txn.currency_id,
                            DeceasedTransaction.amount == anchor_txn.amount,
                            DeceasedTransaction.type == TransactionTypeEnum.deposit,
                            DeceasedTransaction.created_date == anchor_txn.created_date,
                        ).order_by(DeceasedTransaction.id.desc()).first()

                    if not paired_deposit_txn and existing_txn.type == TransactionTypeEnum.deposit:
                        paired_deposit_txn = existing_txn

                    if is_old_distribution:
                        for o_txn in linked_orphan_txns:
                            reverse_existing_txn("orphan", o_txn)
                            db.delete(o_txn)

                        guardian_ids = [
                            e.get("id") for e in getattr(self, "t_table_entities", [])
                            if e.get("kind") == "guardian"
                        ]
                        if guardian_ids:
                            linked_guardian_txns = db.query(GuardianTransaction).filter(
                                GuardianTransaction.guardian_id.in_(guardian_ids),
                                GuardianTransaction.deceased_id == anchor_txn.deceased_id,
                                or_(
                                    GuardianTransaction.deceased_transaction_id == anchor_txn.id,
                                    and_(
                                        GuardianTransaction.currency_id == anchor_txn.currency_id,
                                        GuardianTransaction.created_date == anchor_txn.created_date,
                                        GuardianTransaction.note.like("حصة وصي من توزيع%"),
                                    )
                                ),
                            ).all()
                            for g_txn in linked_guardian_txns:
                                reverse_existing_txn("guardian", g_txn)
                                db.delete(g_txn)

                    old_amount = Decimal(str(anchor_txn.amount or 0))
                    old_type = "deposit" if anchor_txn.type == TransactionTypeEnum.deposit else "withdraw"
                    reverse_old_type = "withdraw" if old_type == "deposit" else "deposit"
                    update_deceased_balance(anchor_txn.deceased_id, anchor_txn.currency_id, old_amount, reverse_old_type)

                    if paired_deposit_txn:
                        paired_old_amount = Decimal(str(paired_deposit_txn.amount or 0))
                        paired_old_type = "deposit" if paired_deposit_txn.type == TransactionTypeEnum.deposit else "withdraw"
                        paired_reverse_type = "withdraw" if paired_old_type == "deposit" else "deposit"
                        update_deceased_balance(
                            paired_deposit_txn.deceased_id,
                            paired_deposit_txn.currency_id,
                            paired_old_amount,
                            paired_reverse_type,
                        )

                    should_distribute = bool(payload.get("should_distribute")) and not is_manual_mode
                    dist_mode = payload.get("distribution_mode") or "بالتساوي"

                    def apply_deceased_txn_fields(txn_obj, kind: str, note_text: str):
                        txn_obj.deceased_id = deceased_id
                        txn_obj.currency_id = local_currency_id
                        txn_obj.amount = amount
                        txn_obj.type = TransactionTypeEnum.deposit if kind == "deposit" else TransactionTypeEnum.withdraw
                        txn_obj.receipt_number = payload.get("receipt_number")
                        txn_obj.payer_name = payload.get("payer_name")
                        txn_obj.payment_method = payload.get("payment_method")
                        txn_obj.check_number = payload.get("check_number")
                        txn_obj.due_date = payload.get("due_date")
                        txn_obj.bank_name = payload.get("bank_name")
                        txn_obj.reference_number = payload.get("reference_number")
                        txn_obj.row_group_key = row_group_key or txn_obj.row_group_key
                        normalized_note = (note_text or "").strip()
                        txn_obj.note = normalized_note or None
                        txn_obj.created_date = effective_created_date

                    if should_distribute:
                        orphans = db.query(Orphan).filter_by(deceased_id=deceased_id).all()
                        if not orphans:
                            raise ValueError("لا يوجد أيتام مسجلون لتوزيع المبلغ عليهم.")

                        beneficiaries = [
                            {
                                "kind": "orphan",
                                "id": orphan.id,
                                "gender": orphan.gender,
                                "name": orphan.name,
                            }
                            for orphan in orphans
                        ]

                        include_guardian_share = bool(payload.get("include_guardian_share"))
                        if include_guardian_share:
                            guardian_link = get_primary_guardian_link_for_deceased(deceased_id)
                            guardian = guardian_link.guardian if guardian_link else None
                            if guardian:
                                beneficiaries.append({
                                    "kind": "guardian",
                                    "id": guardian.id,
                                    "gender": None,
                                    "name": guardian.name,
                                    "orphan_id": guardian_link.orphan_id if guardian_link else None,
                                })

                        shares = calculate_shares(beneficiaries, amount, dist_mode)
                        linked_user_note = (payload.get("note") or default_note or "").strip() or None
                        auto_distribution_note = f"توزيع ({dist_mode}) - المبلغ الموزع: {amount:,.2f}"

                        if txn_type == "deposit":
                            deposit_txn = paired_deposit_txn if paired_deposit_txn else DeceasedTransaction()
                            if deposit_txn.id is None:
                                db.add(deposit_txn)
                            apply_deceased_txn_fields(
                                deposit_txn,
                                "deposit",
                                linked_user_note,
                            )

                            withdraw_txn = anchor_txn if anchor_txn.type == TransactionTypeEnum.withdraw else DeceasedTransaction()
                            if withdraw_txn.id is None:
                                db.add(withdraw_txn)
                            apply_deceased_txn_fields(withdraw_txn, "withdraw", auto_distribution_note)

                            db.flush()
                            parent_txn_id = withdraw_txn.id

                            update_deceased_balance(deceased_id, local_currency_id, amount, "deposit")
                            update_deceased_balance(deceased_id, local_currency_id, amount, "withdraw")

                            result_display_txn_id = stable_display_txn_id
                            result_anchor_txn_id = parent_txn_id
                        else:
                            withdraw_txn = anchor_txn if anchor_txn.type == TransactionTypeEnum.withdraw else DeceasedTransaction()
                            if withdraw_txn.id is None:
                                db.add(withdraw_txn)
                            apply_deceased_txn_fields(withdraw_txn, "withdraw", linked_user_note)

                            if paired_deposit_txn and paired_deposit_txn.id != withdraw_txn.id:
                                db.delete(paired_deposit_txn)

                            db.flush()
                            parent_txn_id = withdraw_txn.id
                            update_deceased_balance(deceased_id, local_currency_id, amount, "withdraw")

                            result_display_txn_id = stable_display_txn_id
                            result_anchor_txn_id = parent_txn_id

                        for beneficiary in beneficiaries:
                            share_amount = Decimal(str(shares.get((beneficiary["kind"], beneficiary["id"]), 0)))
                            if share_amount <= 0:
                                continue

                            if beneficiary["kind"] == "orphan":
                                db.add(Transaction(
                                    orphan_id=beneficiary["id"],
                                    currency_id=local_currency_id,
                                    amount=share_amount,
                                    type=TransactionTypeEnum.deposit,
                                    deceased_transaction_id=parent_txn_id,
                                    row_group_key=row_group_key,
                                    created_date=effective_created_date,
                                    created_at=row_created_at,
                                    note=linked_user_note,
                                ))
                                update_orphan_balance(beneficiary["id"], local_currency_id, share_amount)
                            else:
                                db.add(GuardianTransaction(
                                    guardian_id=beneficiary["id"],
                                    deceased_id=deceased_id,
                                    currency_id=local_currency_id,
                                    deceased_transaction_id=parent_txn_id,
                                    amount=share_amount,
                                    type=TransactionTypeEnum.deposit,
                                    row_group_key=row_group_key,
                                    created_date=effective_created_date,
                                    created_at=row_created_at,
                                    note=linked_user_note,
                                ))
                                apply_balance_delta("guardian", beneficiary["id"], share_amount)

                        return result_display_txn_id, result_anchor_txn_id, True

                    # تعديل حركة غير موزعة (أو التحويل من توزيع إلى غير توزيع)
                    existing_txn.deceased_id = deceased_id
                    existing_txn.currency_id = local_currency_id
                    existing_txn.amount = amount
                    existing_txn.type = TransactionTypeEnum.deposit if txn_type == "deposit" else TransactionTypeEnum.withdraw
                    existing_txn.receipt_number = payload.get("receipt_number")
                    existing_txn.payer_name = payload.get("payer_name")
                    existing_txn.payment_method = payload.get("payment_method")
                    existing_txn.check_number = payload.get("check_number")
                    existing_txn.due_date = payload.get("due_date")
                    existing_txn.bank_name = payload.get("bank_name")
                    existing_txn.reference_number = payload.get("reference_number")
                    normalized_note = (payload.get("note") or default_note or "").strip()
                    existing_txn.note = normalized_note or None
                    existing_txn.created_date = effective_created_date

                    if paired_deposit_txn and paired_deposit_txn.id != existing_txn.id:
                        db.delete(paired_deposit_txn)

                    update_deceased_balance(deceased_id, local_currency_id, amount, txn_type)
                    return stable_display_txn_id, existing_txn.id, True

                new_txn = DeceasedTransaction(
                    deceased_id=deceased_id,
                    currency_id=local_currency_id,
                    amount=amount,
                    type=TransactionTypeEnum.deposit if txn_type == "deposit" else TransactionTypeEnum.withdraw,
                    receipt_number=payload.get("receipt_number"),
                    payer_name=payload.get("payer_name"),
                    payment_method=payload.get("payment_method"),
                    check_number=payload.get("check_number"),
                    due_date=payload.get("due_date"),
                    bank_name=payload.get("bank_name"),
                    reference_number=payload.get("reference_number"),
                    row_group_key=row_group_key,
                    note=(payload.get("note") or default_note or "").strip() or None,
                    created_date=effective_created_date,
                )
                db.add(new_txn)
                db.flush()
                update_deceased_balance(deceased_id, local_currency_id, amount, txn_type)

                if bool(payload.get("should_distribute")) and not is_manual_mode:
                    orphans = db.query(Orphan).filter_by(deceased_id=deceased_id).all()
                    if not orphans:
                        raise ValueError("لا يوجد أيتام مسجلون لتوزيع المبلغ عليهم.")

                    beneficiaries = [
                        {
                            "kind": "orphan",
                            "id": orphan.id,
                            "gender": orphan.gender,
                            "name": orphan.name,
                        }
                        for orphan in orphans
                    ]

                    include_guardian_share = bool(payload.get("include_guardian_share"))
                    if include_guardian_share:
                        guardian_link = get_primary_guardian_link_for_deceased(deceased_id)
                        guardian = guardian_link.guardian if guardian_link else None
                        if guardian:
                            beneficiaries.append({
                                "kind": "guardian",
                                "id": guardian.id,
                                "gender": None,
                                "name": guardian.name,
                                "orphan_id": guardian_link.orphan_id if guardian_link else None,
                            })

                    shares = calculate_shares(beneficiaries, amount, payload.get("distribution_mode") or "بالتساوي")
                    dist_mode = payload.get("distribution_mode") or "بالتساوي"
                    linked_user_note = (payload.get("note") or default_note or "").strip() or None
                    auto_distribution_note = f"توزيع ({dist_mode}) - المبلغ الموزع: {amount:,.2f}"

                    parent_txn_id = new_txn.id
                    if txn_type == "deposit":
                        auto_withdraw = DeceasedTransaction(
                            deceased_id=deceased_id,
                            currency_id=local_currency_id,
                            amount=amount,
                            type=TransactionTypeEnum.withdraw,
                            payment_method=payload.get("payment_method"),
                            row_group_key=row_group_key,
                            note=auto_distribution_note,
                            created_date=effective_created_date,
                        )
                        db.add(auto_withdraw)
                        db.flush()
                        update_deceased_balance(deceased_id, local_currency_id, amount, "withdraw")
                        parent_txn_id = auto_withdraw.id

                    for beneficiary in beneficiaries:
                        share_amount = Decimal(str(shares.get((beneficiary["kind"], beneficiary["id"]), 0)))
                        if share_amount <= 0:
                            continue
                        if beneficiary["kind"] == "orphan":
                            db.add(Transaction(
                                orphan_id=beneficiary["id"],
                                currency_id=local_currency_id,
                                amount=share_amount,
                                type=TransactionTypeEnum.deposit,
                                deceased_transaction_id=parent_txn_id,
                                row_group_key=row_group_key,
                                created_date=effective_created_date,
                                created_at=row_created_at,
                                note=linked_user_note,
                            ))
                            update_orphan_balance(beneficiary["id"], local_currency_id, share_amount)
                        else:
                            db.add(GuardianTransaction(
                                guardian_id=beneficiary["id"],
                                deceased_id=deceased_id,
                                currency_id=local_currency_id,
                                deceased_transaction_id=parent_txn_id,
                                amount=share_amount,
                                type=TransactionTypeEnum.deposit,
                                row_group_key=row_group_key,
                                created_date=effective_created_date,
                                created_at=row_created_at,
                                note=linked_user_note,
                            ))
                            apply_balance_delta("guardian", beneficiary["id"], share_amount)

                    display_txn_id = new_txn.id if txn_type == "deposit" else parent_txn_id
                    return display_txn_id, parent_txn_id, False

                # حركة جديدة بدون توزيع: ثبّت رقم الحركة على الصف
                return new_txn.id, new_txn.id, False

            pending_row_updates = []

            def reverse_existing_txn(kind, txn):
                amount = Decimal(str(txn.amount or 0))
                if txn.type == TransactionTypeEnum.deposit:
                    apply_balance_delta(kind, txn.orphan_id if kind == "orphan" else txn.guardian_id, -amount)
                else:
                    apply_balance_delta(kind, txn.orphan_id if kind == "orphan" else txn.guardian_id, amount)

            def parse_optional_due_date(raw_due_date):
                if raw_due_date is None:
                    return None
                if isinstance(raw_due_date, datetime):
                    return raw_due_date.date()
                if isinstance(raw_due_date, date):
                    return raw_due_date

                due_text = str(raw_due_date or "").strip()
                if not due_text:
                    return None

                q_date = QDate.fromString(due_text, "dd/MM/yyyy")
                if q_date.isValid():
                    return q_date.toPyDate()

                return try_get_date(due_text)

            def extract_extra_txn_fields(payload):
                payload = payload if isinstance(payload, dict) else {}
                return {
                    "document_number": (payload.get("document_number") or "").strip() or None,
                    "person_name": (payload.get("person_name") or "").strip() or None,
                    "payment_method": (payload.get("payment_method") or "").strip() or None,
                    "check_number": (payload.get("check_number") or "").strip() or None,
                    "due_date": parse_optional_due_date(payload.get("due_date")),
                    "bank_name": (payload.get("bank_name") or "").strip() or None,
                    "reference_number": (payload.get("reference_number") or "").strip() or None,
                }

            def create_txn(kind, person_id, amount, txn_type, created_date, created_at, note, row_group_key=None, extra_payload=None):
                amount = Decimal(str(amount or 0))
                if amount <= 0:
                    return

                available = get_available_balance(kind, person_id)
                if txn_type == TransactionTypeEnum.withdraw and available < amount:
                    raise ValueError(f"الرصيد غير كافٍ للسحب في الصف")

                extra_fields = extract_extra_txn_fields(extra_payload)

                if kind == "orphan":
                    db.add(Transaction(
                        orphan_id=person_id,
                        currency_id=currency_id,
                        amount=amount,
                        type=txn_type,
                        row_group_key=row_group_key,
                        created_date=created_date,
                        created_at=created_at,
                        note=note,
                        document_number=extra_fields["document_number"],
                        person_name=extra_fields["person_name"],
                        payment_method=extra_fields["payment_method"],
                        check_number=extra_fields["check_number"],
                        due_date=extra_fields["due_date"],
                        bank_name=extra_fields["bank_name"],
                        reference_number=extra_fields["reference_number"],
                    ))
                else:
                    db.add(GuardianTransaction(
                        guardian_id=person_id,
                        deceased_id=self.current_deceased_for_t_table.id if self.current_deceased_for_t_table else None,
                        currency_id=currency_id,
                        amount=amount,
                        type=txn_type,
                        row_group_key=row_group_key,
                        created_date=created_date,
                        created_at=created_at,
                        note=note,
                        document_number=extra_fields["document_number"],
                        person_name=extra_fields["person_name"],
                        payment_method=extra_fields["payment_method"],
                        check_number=extra_fields["check_number"],
                        due_date=extra_fields["due_date"],
                        bank_name=extra_fields["bank_name"],
                        reference_number=extra_fields["reference_number"],
                    ))

                delta = amount if txn_type == TransactionTypeEnum.deposit else -amount
                apply_balance_delta(kind, person_id, delta)

            def build_desired_amount_map(rows, id_key):
                result = {}
                for entry in rows or []:
                    person_id = entry.get(id_key)
                    if not person_id:
                        continue
                    dep = Decimal(str(entry.get("deposit", Decimal('0')) or 0))
                    wd = Decimal(str(entry.get("withdraw", Decimal('0')) or 0))
                    if dep <= 0 and wd <= 0:
                        continue
                    result[person_id] = {
                        "deposit": dep,
                        "withdraw": wd,
                    }
                return result

            def build_existing_amount_map(txns, kind):
                result = {}
                for txn in txns or []:
                    person_id = txn.orphan_id if kind == "orphan" else txn.guardian_id
                    if not person_id:
                        continue
                    if person_id not in result:
                        result[person_id] = {
                            "deposit": Decimal('0'),
                            "withdraw": Decimal('0'),
                        }
                    amount = Decimal(str(txn.amount or 0))
                    if txn.type == TransactionTypeEnum.deposit:
                        result[person_id]["deposit"] += amount
                    else:
                        result[person_id]["withdraw"] += amount
                return result

            def normalize_date_only(value):
                if not value:
                    return None
                try:
                    return value.date() if hasattr(value, "date") else value
                except Exception:
                    return value

            deceased_validation_cache = {}

            def get_deceased_available_for_validation(local_deceased_id, local_currency_id):
                key = (local_deceased_id, local_currency_id)
                if key in deceased_validation_cache:
                    return deceased_validation_cache[key]

                bal_rec = db.query(DeceasedBalance).filter_by(
                    deceased_id=local_deceased_id,
                    currency_id=local_currency_id,
                ).first()
                deceased_validation_cache[key] = Decimal(str(bal_rec.balance or 0)) if bal_rec else Decimal('0')
                return deceased_validation_cache[key]

            def set_deceased_available_for_validation(local_deceased_id, local_currency_id, value: Decimal):
                key = (local_deceased_id, local_currency_id)
                deceased_validation_cache[key] = Decimal(str(value or 0))

            def calculate_row_manual_distribution_total(row_item):
                total = Decimal('0')
                for orphan_tx in row_item.get("orphans_transactions", []) or []:
                    dep = Decimal(str(orphan_tx.get("deposit", Decimal('0')) or 0))
                    if dep > 0:
                        total += dep

                for guardian_tx in row_item.get("guardian_transactions", []) or []:
                    dep = Decimal(str(guardian_tx.get("deposit", Decimal('0')) or 0))
                    if dep > 0:
                        total += dep

                return total

            def is_manual_distribution_mode(mode_value):
                normalized = str(mode_value or "").strip()
                return normalized == "يدوي"

            def get_row_pending_new_deceased_net_delta(action_payload):
                if not isinstance(action_payload, dict):
                    return Decimal('0')
                if action_payload.get("status") != "pending":
                    return Decimal('0')
                if action_payload.get("target_txn_id"):
                    return Decimal('0')

                payload = action_payload.get("payload") or {}
                amount = Decimal(str(payload.get("amount") or 0))
                txn_type = payload.get("type")
                should_distribute = bool(payload.get("should_distribute"))
                is_manual_mode = is_manual_distribution_mode(payload.get("distribution_mode"))

                if amount <= 0 or txn_type not in ("deposit", "withdraw"):
                    return Decimal('0')

                if should_distribute and not is_manual_mode:
                    return Decimal('0') if txn_type == "deposit" else -amount
                return amount if txn_type == "deposit" else -amount

            def get_row_deceased_id_for_manual_distribution(action_payload):
                if (
                    isinstance(action_payload, dict)
                    and action_payload.get("status") == "pending"
                    and isinstance(action_payload.get("payload"), dict)
                ):
                    payload_deceased_id = (action_payload.get("payload") or {}).get("deceased_id")
                    if payload_deceased_id:
                        return payload_deceased_id
                return self.current_deceased_for_t_table.id if self.current_deceased_for_t_table else None

            def get_row_manual_distribution_cap_amount(action_payload, local_currency_id):
                if not isinstance(action_payload, dict):
                    return None

                if (
                    action_payload.get("status") == "pending"
                    and isinstance(action_payload.get("payload"), dict)
                ):
                    payload = action_payload.get("payload") or {}
                    if is_manual_distribution_mode(payload.get("distribution_mode")):
                        pending_amount = Decimal(str(payload.get("amount") or 0))
                        return pending_amount if pending_amount > 0 else None

                if action_payload.get("status") == "saved" and bool(action_payload.get("manual_linked")):
                    probe_ids = [
                        action_payload.get("txn_id"),
                        action_payload.get("distribution_anchor_txn_id"),
                    ]
                    for probe_id in probe_ids:
                        if not probe_id:
                            continue
                        probe_txn = db.query(DeceasedTransaction).filter_by(id=probe_id).first()
                        if not probe_txn:
                            continue
                        if local_currency_id and probe_txn.currency_id != local_currency_id:
                            continue
                        probe_amount = Decimal(str(probe_txn.amount or 0))
                        if probe_amount > 0:
                            return probe_amount

                return None

            def reverse_and_delete_existing_auto_manual_withdraw(local_deceased_id, local_currency_id, row_created_at_dt, row_group_key=None):
                if not local_deceased_id:
                    return

                query = db.query(DeceasedTransaction).filter(
                    DeceasedTransaction.deceased_id == local_deceased_id,
                    DeceasedTransaction.currency_id == local_currency_id,
                    DeceasedTransaction.type == TransactionTypeEnum.withdraw,
                    DeceasedTransaction.is_auto_manual_distribution == True,
                )

                if row_group_key:
                    query = query.filter(DeceasedTransaction.row_group_key == row_group_key)
                else:
                    query = query.filter(DeceasedTransaction.created_date == row_created_at_dt)

                existing_auto_withdraws = query.all()

                for auto_txn in existing_auto_withdraws:
                    update_deceased_balance(
                        auto_txn.deceased_id,
                        auto_txn.currency_id,
                        Decimal(str(auto_txn.amount or 0)),
                        "deposit",
                    )
                    db.delete(auto_txn)

            def create_auto_manual_withdraw(local_deceased_id, local_currency_id, amount: Decimal, row_created_at_dt, row_group_key=None):
                if not local_deceased_id:
                    return
                if amount <= 0:
                    return

                db.add(DeceasedTransaction(
                    deceased_id=local_deceased_id,
                    currency_id=local_currency_id,
                    amount=amount,
                    type=TransactionTypeEnum.withdraw,
                    payment_method="---",
                    note=None,
                    is_auto_manual_distribution=True,
                    row_group_key=row_group_key,
                    created_date=row_created_at_dt,
                ))
                update_deceased_balance(local_deceased_id, local_currency_id, amount, "withdraw")

            def get_existing_auto_manual_withdraw_amount(local_deceased_id, local_currency_id, row_created_at_dt, row_group_key=None):
                if not local_deceased_id:
                    return Decimal('0')

                query = db.query(func.coalesce(func.sum(DeceasedTransaction.amount), 0)).filter(
                    DeceasedTransaction.deceased_id == local_deceased_id,
                    DeceasedTransaction.currency_id == local_currency_id,
                    DeceasedTransaction.type == TransactionTypeEnum.withdraw,
                    DeceasedTransaction.is_auto_manual_distribution == True,
                )

                if row_group_key:
                    query = query.filter(DeceasedTransaction.row_group_key == row_group_key)
                elif row_created_at_dt:
                    query = query.filter(DeceasedTransaction.created_date == row_created_at_dt)
                else:
                    return Decimal('0')

                amount_sum = query.scalar()

                return Decimal(str(amount_sum or 0))

            def apply_saved_distribution_row_date(action_payload, desired_created_date):
                if not isinstance(action_payload, dict) or not desired_created_date:
                    return

                anchor_txn_id = action_payload.get("distribution_anchor_txn_id") or action_payload.get("txn_id")
                if not anchor_txn_id:
                    return

                anchor_txn = db.query(DeceasedTransaction).filter_by(id=anchor_txn_id).first()
                if not anchor_txn:
                    return

                desired_date_only = normalize_date_only(desired_created_date)

                linked_orphan_txns = db.query(Transaction).filter_by(
                    deceased_transaction_id=anchor_txn.id
                ).all()
                linked_guardian_txns = db.query(GuardianTransaction).filter_by(
                    deceased_transaction_id=anchor_txn.id
                ).all()

                for txn in linked_orphan_txns:
                    if normalize_date_only(getattr(txn, "created_date", None)) != desired_date_only:
                        txn.created_date = desired_created_date

                for txn in linked_guardian_txns:
                    if normalize_date_only(getattr(txn, "created_date", None)) != desired_date_only:
                        txn.created_date = desired_created_date

                if normalize_date_only(getattr(anchor_txn, "created_date", None)) != desired_date_only:
                    anchor_txn.created_date = desired_created_date

                if anchor_txn.type == TransactionTypeEnum.withdraw:
                    paired_deposit_txn = db.query(DeceasedTransaction).filter(
                        DeceasedTransaction.id != anchor_txn.id,
                        DeceasedTransaction.deceased_id == anchor_txn.deceased_id,
                        DeceasedTransaction.currency_id == anchor_txn.currency_id,
                        DeceasedTransaction.amount == anchor_txn.amount,
                        DeceasedTransaction.type == TransactionTypeEnum.deposit,
                    ).order_by(DeceasedTransaction.id.desc()).first()
                    if paired_deposit_txn and normalize_date_only(getattr(paired_deposit_txn, "created_date", None)) != desired_date_only:
                        paired_deposit_txn.created_date = desired_created_date

            for item in data:
                table_row = item.get("_table_row", "-")
                created_date = parse_and_validate_date(item.get("date", ""))
                deceased_action_payload = item.get("deceased_action") if isinstance(item.get("deceased_action"), dict) else None
                pending_dist_mode = (
                    (deceased_action_payload.get("payload") or {}).get("distribution_mode")
                    if isinstance(deceased_action_payload, dict)
                    else None
                )
                is_pending_manual_distribution = is_manual_distribution_mode(pending_dist_mode)
                is_pending_distribution = bool(
                    deceased_action_payload
                    and deceased_action_payload.get("status") == "pending"
                    and isinstance(deceased_action_payload.get("payload"), dict)
                    and deceased_action_payload.get("payload", {}).get("should_distribute")
                    and not is_pending_manual_distribution
                )
                has_pending_deceased_txn = bool(
                    deceased_action_payload
                    and deceased_action_payload.get("status") == "pending"
                    and isinstance(deceased_action_payload.get("payload"), dict)
                    and Decimal(str((deceased_action_payload.get("payload") or {}).get("amount") or 0)) > 0
                    and (deceased_action_payload.get("payload") or {}).get("type") in ("deposit", "withdraw")
                )

                is_saved_distribution = False
                if deceased_action_payload and deceased_action_payload.get("status") == "saved":
                    anchor_id = deceased_action_payload.get("distribution_anchor_txn_id")
                    display_id = deceased_action_payload.get("txn_id")
                    probe_ids = [tx_id for tx_id in [anchor_id, display_id] if tx_id]
                    for probe_id in probe_ids:
                        linked_count = db.query(Transaction).filter_by(deceased_transaction_id=probe_id).count()
                        if linked_count > 0:
                            is_saved_distribution = True
                            break

                # في حالة التوزيع المحفوظ بدون تعديل معلّق: لا تعيد كتابة حركات الورثة حتى لا يضيع الربط.
                preserve_saved_distribution_row = is_saved_distribution and not is_pending_distribution
                skip_manual_entity_transactions = is_pending_distribution or preserve_saved_distribution_row
                should_link_manual_distribution = has_pending_deceased_txn or is_saved_distribution

                row_key = item.get("row_key")
                is_existing_row = bool(item.get("id") and row_key)
                row_group_key = None
                if is_existing_row:
                    row_created_at = self._parse_row_datetime_key(row_key)
                    if not row_created_at:
                        row_group_key = str(row_key or "").strip() or None
                        if not row_group_key:
                            raise ValueError(f"تعذر قراءة معرف الصف الأصلي في الصف ({table_row})")
                else:
                    row_created_at = datetime.now()
                    row_group_key = f"grp_{uuid4().hex}"

                if is_existing_row and row_group_key and not row_created_at:
                    sample_txn = db.query(Transaction).filter(
                        Transaction.row_group_key == row_group_key,
                        Transaction.currency_id == currency_id,
                    ).order_by(Transaction.id.asc()).first()
                    if not sample_txn:
                        sample_txn = db.query(GuardianTransaction).filter(
                            GuardianTransaction.row_group_key == row_group_key,
                            GuardianTransaction.currency_id == currency_id,
                        ).order_by(GuardianTransaction.id.asc()).first()
                    if sample_txn:
                        row_created_at = getattr(sample_txn, "created_at", None) or getattr(sample_txn, "created_date", None)
                    else:
                        row_created_at = datetime.now()

                effective_created_date = created_date if created_date else row_created_at

                if (
                    not should_link_manual_distribution
                    and isinstance(deceased_action_payload, dict)
                    and deceased_action_payload.get("status") == "saved"
                    and bool(deceased_action_payload.get("manual_linked"))
                ):
                    saved_deceased_id = get_row_deceased_id_for_manual_distribution(deceased_action_payload)
                    saved_auto_amount = get_existing_auto_manual_withdraw_amount(
                        saved_deceased_id,
                        currency_id,
                        row_created_at if is_existing_row else None,
                        row_group_key,
                    )
                    if saved_auto_amount > 0:
                        should_link_manual_distribution = True

                row_manual_distribution_total = calculate_row_manual_distribution_total(item)
                if row_manual_distribution_total > 0 and self.current_deceased_for_t_table and should_link_manual_distribution and not skip_manual_entity_transactions:
                    validation_deceased_id = get_row_deceased_id_for_manual_distribution(deceased_action_payload)
                    manual_cap_amount = get_row_manual_distribution_cap_amount(deceased_action_payload, currency_id)

                    if manual_cap_amount is not None:
                        if row_manual_distribution_total > manual_cap_amount:
                            raise ValueError(
                                f"الصف ({table_row}): المبلغ الموزع يدويًا ({row_manual_distribution_total:,.2f}) "
                                f"يتجاوز مبلغ حركة المتوفى المدخلة ({manual_cap_amount:,.2f})."
                            )
                        set_deceased_available_for_validation(
                            validation_deceased_id,
                            currency_id,
                            manual_cap_amount - row_manual_distribution_total,
                        )
                    else:

                        projected_delta = get_row_pending_new_deceased_net_delta(deceased_action_payload)
                        available_before = get_deceased_available_for_validation(validation_deceased_id, currency_id)
                        existing_auto_amount = get_existing_auto_manual_withdraw_amount(
                            validation_deceased_id,
                            currency_id,
                            row_created_at if is_existing_row else None,
                            row_group_key,
                        )
                        available_for_row = available_before + projected_delta + existing_auto_amount

                        if row_manual_distribution_total > available_for_row:
                            raise ValueError(
                                f"الصف ({table_row}): المبلغ الموزع يدويًا ({row_manual_distribution_total:,.2f}) "
                                f"يتجاوز الرصيد المتاح للمتوفى ({available_for_row:,.2f})."
                            )

                        set_deceased_available_for_validation(
                            validation_deceased_id,
                            currency_id,
                            available_for_row - row_manual_distribution_total,
                        )

                if self.current_deceased_for_t_table and not should_link_manual_distribution:
                    unlink_deceased_id = get_row_deceased_id_for_manual_distribution(deceased_action_payload)
                    reverse_and_delete_existing_auto_manual_withdraw(
                        unlink_deceased_id,
                        currency_id,
                        row_created_at,
                        row_group_key,
                    )

                if is_existing_row:
                    if preserve_saved_distribution_row:
                        apply_saved_distribution_row_date(
                            item.get("deceased_action"),
                            effective_created_date,
                        )
                        continue

                    orphan_ids = [o.get("orphan_id") for o in item.get("orphans_transactions", []) if o.get("orphan_id")]
                    guardian_ids = [g.get("guardian_id") for g in item.get("guardian_transactions", []) if g.get("guardian_id")]

                    old_orphan_txns = []
                    old_guardian_txns = []
                    if orphan_ids:
                        orphan_old_query = db.query(Transaction).filter(
                            Transaction.orphan_id.in_(orphan_ids),
                            Transaction.currency_id == currency_id,
                        )
                        if row_group_key:
                            orphan_old_query = orphan_old_query.filter(Transaction.row_group_key == row_group_key)
                        else:
                            orphan_old_query = orphan_old_query.filter(Transaction.created_at == row_created_at)
                        old_orphan_txns = orphan_old_query.all()

                    if guardian_ids:
                        guardian_old_query = db.query(GuardianTransaction).filter(
                            GuardianTransaction.guardian_id.in_(guardian_ids),
                            GuardianTransaction.deceased_id == self.current_deceased_for_t_table.id,
                            GuardianTransaction.currency_id == currency_id,
                        )
                        if row_group_key:
                            guardian_old_query = guardian_old_query.filter(GuardianTransaction.row_group_key == row_group_key)
                        else:
                            guardian_old_query = guardian_old_query.filter(GuardianTransaction.created_at == row_created_at)
                        old_guardian_txns = guardian_old_query.all()

                    # عدّل فقط ما تغيّر فعلياً: إذا لا يوجد تغيير نتجاوز هذا الصف بالكامل.
                    has_pending_deceased_change = bool(
                        deceased_action_payload
                        and deceased_action_payload.get("status") == "pending"
                    )
                    if not has_pending_deceased_change:
                        desired_orphan_map = build_desired_amount_map(item.get("orphans_transactions", []), "orphan_id")
                        desired_guardian_map = build_desired_amount_map(item.get("guardian_transactions", []), "guardian_id")

                        existing_orphan_map = build_existing_amount_map(old_orphan_txns, "orphan")
                        existing_guardian_map = build_existing_amount_map(old_guardian_txns, "guardian")

                        desired_note = (item.get("note") or "").strip()
                        existing_notes = {
                            (txn.note or "").strip()
                            for txn in [*old_orphan_txns, *old_guardian_txns]
                        }
                        notes_equal = (
                            (not existing_notes and desired_note == "")
                            or existing_notes == {desired_note}
                        )

                        desired_date_only = normalize_date_only(effective_created_date)
                        existing_dates = {
                            normalize_date_only(getattr(txn, "created_date", None))
                            for txn in [*old_orphan_txns, *old_guardian_txns]
                            if getattr(txn, "created_date", None) is not None
                        }
                        dates_equal = (
                            (not existing_dates and desired_date_only is None)
                            or existing_dates == {desired_date_only}
                        )

                        if (
                            desired_orphan_map == existing_orphan_map
                            and desired_guardian_map == existing_guardian_map
                            and notes_equal
                            and dates_equal
                        ):
                            continue

                    for old_txn in old_orphan_txns:
                        reverse_existing_txn("orphan", old_txn)
                        db.delete(old_txn)

                    for old_txn in old_guardian_txns:
                        reverse_existing_txn("guardian", old_txn)
                        db.delete(old_txn)

                    db.flush()

                if not skip_manual_entity_transactions:
                    for o in item.get("orphans_transactions", []):
                        dep_amount = o.get("deposit", Decimal('0'))
                        wd_amount = o.get("withdraw", Decimal('0'))
                        if dep_amount > 0 and wd_amount > 0:
                            raise ValueError(f"لا يمكن إدخال إيداع وسحب معاً لليتيم '{o.get('orphan_name', '')}' في نفس الصف ({table_row})")

                        if dep_amount > 0:
                            create_txn(
                                "orphan",
                                o["orphan_id"],
                                dep_amount,
                                TransactionTypeEnum.deposit,
                                effective_created_date,
                                row_created_at,
                                item.get("note", ""),
                                row_group_key,
                                o,
                            )
                        if wd_amount > 0:
                            available = get_available_balance("orphan", o["orphan_id"])
                            if available < wd_amount:
                                raise ValueError(
                                    f"رصيد اليتيم '{o.get('orphan_name', '')}' غير كافٍ للسحب في الصف ({table_row}). "
                                    f"المتاح: {available:,.2f}"
                                )
                            create_txn(
                                "orphan",
                                o["orphan_id"],
                                wd_amount,
                                TransactionTypeEnum.withdraw,
                                effective_created_date,
                                row_created_at,
                                item.get("note", ""),
                                row_group_key,
                                o,
                            )

                    for g in item.get("guardian_transactions", []):
                        dep_amount = g.get("deposit", Decimal('0'))
                        wd_amount = g.get("withdraw", Decimal('0'))
                        if dep_amount > 0 and wd_amount > 0:
                            raise ValueError(f"لا يمكن إدخال إيداع وسحب معاً للوصي '{g.get('guardian_name', '')}' في نفس الصف ({table_row})")

                        if dep_amount > 0:
                            create_txn(
                                "guardian",
                                g["guardian_id"],
                                dep_amount,
                                TransactionTypeEnum.deposit,
                                effective_created_date,
                                row_created_at,
                                item.get("note", ""),
                                row_group_key,
                                g,
                            )
                        if wd_amount > 0:
                            available = get_available_balance("guardian", g["guardian_id"])
                            if available < wd_amount:
                                raise ValueError(
                                    f"رصيد الوصي '{g.get('guardian_name', '')}' غير كافٍ للسحب في الصف ({table_row}). "
                                    f"المتاح: {available:,.2f}"
                                )
                            create_txn(
                                "guardian",
                                g["guardian_id"],
                                wd_amount,
                                TransactionTypeEnum.withdraw,
                                effective_created_date,
                                row_created_at,
                                item.get("note", ""),
                                row_group_key,
                                g,
                            )

                created_deceased_result = create_deceased_txn_from_pending(
                    item.get("deceased_action"),
                    effective_created_date,
                    item.get("note", ""),
                    row_group_key,
                )
                if created_deceased_result:
                    display_txn_id, anchor_txn_id, is_update = created_deceased_result
                    manual_linked_flag = bool(
                        has_pending_deceased_txn and not is_pending_distribution
                    )
                    pending_row_updates.append((
                        item.get("_table_row", 0) - 1,
                        display_txn_id,
                        anchor_txn_id,
                        is_update,
                        manual_linked_flag,
                    ))

                if not skip_manual_entity_transactions and self.current_deceased_for_t_table and should_link_manual_distribution:
                    manual_dist_deceased_id = get_row_deceased_id_for_manual_distribution(deceased_action_payload)
                    reverse_and_delete_existing_auto_manual_withdraw(
                        manual_dist_deceased_id,
                        currency_id,
                        row_created_at,
                        row_group_key,
                    )
                    create_auto_manual_withdraw(
                        manual_dist_deceased_id,
                        currency_id,
                        row_manual_distribution_total,
                        row_created_at,
                        row_group_key,
                    )
            db.commit()

            for row_idx, display_txn_id, anchor_txn_id, is_update, manual_linked_flag in pending_row_updates:
                if row_idx < 2 or row_idx >= self.t_table.rowCount():
                    continue
                _, _, action_col, _, _ = self._get_financial_table_special_columns(self.t_table)
                item_widget = self.t_table.item(row_idx, action_col)
                if not item_widget:
                    continue
                item_widget.setText(f"تم التعديل #{display_txn_id}" if is_update else f"تمت الإضافة #{display_txn_id}")
                item_widget.setData(Qt.ItemDataRole.UserRole, {
                    "status": "saved",
                    "txn_id": display_txn_id,
                    "distribution_anchor_txn_id": anchor_txn_id,
                    "manual_linked": manual_linked_flag,
                })
        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "تنبيه", str(ve))
            return
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء حفظ البيانات: {e}")
            return
        QMessageBox.information(self, "نجاح", success_message)
        if self.current_deceased_for_t_table:
            self.load_historical_data_for_deceased(self.current_deceased_for_t_table)

    def update_t_table_buttons_state(self):
        """تحديث حالة أزرار الإضافة والحذف بناءً على وجود بيانات أو هياكل في الجدول"""
        # فعّل الأزرار إذا كان الجدول يحتوي على أعمدة (أي تم تحضيره بهياكل)
        has_structure = self.t_table.columnCount() > 0
        self.add_new_row_t_btn.setEnabled(has_structure)
        if hasattr(self, "add_new_row_to_t_table_btn"):
            self.add_new_row_to_t_table_btn.setEnabled(has_structure)
        self.remove_selected_row_t_btn.setEnabled(has_structure)

    def open_add_t_table_row_dialog(self):
        """فتح نافذة إدخال بيانات صف جديد ثم حفظه مباشرة في قاعدة البيانات."""
        if self.t_table.columnCount() == 0:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار متوفى أولاً لتجهيز جدول المعاملات.")
            return

        dialog = AddTTableRowDialog(parent=self)
        if not dialog.exec():
            return

        row_data = dialog.get_data() or {}
        self.save_t_table_dialog_row_directly(row_data)

    def save_t_table_dialog_row_directly(self, row_data):
        """حفظ مباشر اختياري من بيانات AddTTableRowDialog بدون التأثير على تدفق الجدول القديم."""
        direct_payload = self._build_direct_save_payload_from_t_table_dialog(row_data)
        self.save_transactions(data_override=direct_payload, success_message="تم حفظ الحركة مباشرة بنجاح.")
    
    def add_row_to_t_table(self, date_text: str = "", note_text: str = ""):
        """إضافة صف جديد للبيانات مع مراعاة العناوين المدمجة"""
        row_position = self.t_table.rowCount()
        self.t_table.insertRow(row_position)
        self._initialize_financial_table_row(self.t_table, row_position)

        if date_text:
            date_item = self.t_table.item(row_position, 1) or QTableWidgetItem("")
            date_item.setText(date_text)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.t_table.setItem(row_position, 1, date_item)

        if note_text:
            _, note_col, _, _, _ = self._get_financial_table_special_columns(self.t_table)
            note_item = self.t_table.item(row_position, note_col) or QTableWidgetItem("")
            note_item.setText(self._sanitize_user_visible_note(note_text))
            note_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.t_table.setItem(row_position, note_col, note_item)

        self._refresh_financial_entity_header_balances(self.t_table)
        
        # تحديث حالة الأزرار
        self.update_t_table_buttons_state()
    
    def remove_selected_row_from_t_table(self):
        """حذف الصف المحدد مع حماية صفوف العناوين"""
        row = self.t_table.currentRow()
        
        # التحقق من وجود تحديد
        if row == -1:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد الصف المراد حذفه أولاً.")
            return
            
        # منع حذف صفوف العناوين المدمجة (الصف 0 و 1)
        if row < 2:
            # QMessageBox.critical(self, "خطأ", "لا يمكن حذف صفوف العناوين المدمجة.")
            return
        
        id_item = self.t_table.item(row, 0) 
        print(f"Attempting to delete row {row} with ID item: {id_item.text() if id_item else 'None'}")
        if id_item and id_item.text():
            return
        
        # # تأكيد الحذف
        # reply = QMessageBox.question(self, 'تأكيد الحذف', 
        #                             "هل أنت متأكد من حذف هذا السطر المالي؟",
        #                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                    
        # if reply == QMessageBox.StandardButton.Yes:
        self.t_table.removeRow(row)
        self._refresh_financial_entity_header_balances(self.t_table)
        
        # تحديث حالة الأزرار
        self.update_t_table_buttons_state()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.shown:
            self.shown = True
            self.setStyleSheet(self.styleSheet())

    def init_ui(self):
        self.tabWidget.tabBar().setVisible(False)
        self.disable_item(self.listWidget.item(1)) # Disable Person Record tab initially
        self.set_sellected_list_item(self.listWidget, 0)
        
        header = self.permissions_table.horizontalHeader()
        # أول عمود يتمدد
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # باقي الأعمدة حجمها حسب المحتوى
        for i in range(1, self.permissions_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        
        # اسم البنك (ILS)
        self.label_146.hide()
        self.lineEdit_14.hide()
        # اسم البنك (USD)
        self.label_150.hide()
        self.lineEdit_19.hide()
        # اسم البنك (JOD)
        self.label_156.hide()
        self.lineEdit_26.hide()
        # اسم البنك (EUR)
        self.label_162.hide()
        self.lineEdit_33.hide()
        # =====================
        # رصيد الشيكل (شيك)
        self.label_143.hide()
        self.label_145.hide()
        self.lineEdit_12.hide()
        self.lineEdit_13.hide()
        # رصيد الدولار (شيك)
        self.label_149.hide()
        self.label_151.hide()
        self.lineEdit_17.hide()
        self.lineEdit_18.hide()
        # رصيد الدينار (شيك)
        self.label_155.hide()
        self.label_157.hide()
        self.lineEdit_24.hide()
        self.lineEdit_25.hide()
        # رصيد اليورو (شيك)
        self.label_161.hide()
        self.label_163.hide()
        self.lineEdit_31.hide()
        self.lineEdit_32.hide()
        # =====================
        # رقم الحوالة (شيكل)
        self.label_147.hide()
        self.lineEdit_15.hide()
        # رقم الحوالة (دولار)
        self.label_152.hide()
        self.lineEdit_20.hide()
        # رقم الحوالة (دينار)
        self.label_158.hide()
        self.lineEdit_27.hide()
        # رقم الحوالة (يورو)
        self.label_164.hide()
        self.lineEdit_34.hide()
        
        self.user_id_input.hide()
        self.toggle_user_inputs(False)
        
        self.add_deceased_orphans_table.setColumnHidden(0, True)
        self.add_guardian_orphans_table.setColumnHidden(0, True)
        self.detail_orphan_transactions_table.setColumnHidden(0, True)
        self.detail_deceased_transactions_table.setColumnHidden(0, True)
        self.transactions_table_3.setColumnHidden(0, True)
        self.detail_deceased_orphans_table.setColumnHidden(0, True)
        self.detail_guardian_orphans_table.setColumnHidden(0, True)
        self.t_table.setColumnHidden(0, True)
        
        # ضبط حجم الأعمدة في جداول المعاملات لتناسب المحتوى
        self.detail_deceased_transactions_table.resizeColumnsToContents()
        self.detail_deceased_transactions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # self.t_table.resizeColumnsToContents()
        # self.t_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # self.t_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # self.t_table.resizeColumnsToContents()
        # self.t_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # # أضف هذه الأسطر في نهاية دالة load_historical_data_for_deceased
        # header = self.t_table.horizontalHeader()

        # # 1. تفعيل خاصية تمدد الأعمدة لتناسب المحتوى (يمنع التكدس الظاهر في الصورة)
        # header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # # 2. تحديد عرض أدنى لأعمدة الإيداع والسحب لضمان وضوح النص
        # for col in range(self.t_table.columnCount()):
        #     self.t_table.setColumnWidth(col, 100) 

        # # 3. السماح بنزول النص لسطر جديد في العناوين (Word Wrap)
        # self.t_table.setWordWrap(True)
        
        # إخفاء بعض الحقول
        self.role_id_input.hide()
        self.widget_34.hide()
        self.lineEdit_37.hide()
        self.lineEdit_38.hide()
        self.lineEdit_39.hide()
        self.lineEdit_40.hide()
        self.lineEdit_41.hide()
        
        self.role_delete_btn.setEnabled(False) # تعطيل زر الحذف حتى يتم إدخال اسم دور
        self._enable_excel_like_table(self.t_table, header_rows=2)
        self._setup_t_table_column_width_controls()

    def check_permissions(self):
        # خريطة تربط اسم الصلاحية برقم العنصر في القائمة
        permissions_map = {
            # 'Home': 0,
            # 'PersonDetail': 1,
            'NewPerson': 2,
            # 'DeceasedList': 3,
            # 'GuardiansList': 4,
            # 'OrphansList': 5,
            # 'OrphansOver18': 6,
            'Users': 7,
            'Roles': 8,
            'Permissions': 9,
            'ActivityLogs': 10,
            'Settings': 11,
        }

        # التحقق من عناصر القائمة (ListWidget)
        for perm_name, item_index in permissions_map.items():
            has_perm = has_permission(self.current_user, perm_name, PermissionEnum.view)
            # إخفاء العنصر إذا لم تكن هناك صلاحية
            self.listWidget.setRowHidden(item_index, not has_perm)

        # التحقق من الأزرار المنفصلة (التقارير)
        can_view_reports = has_permission(self.current_user, 'Reports', PermissionEnum.create)
        self.detail_export_btn.setEnabled(can_view_reports)
        self.orphans_monthly_report.setEnabled(can_view_reports)
        
        self.detail_save_btn.setEnabled(has_permission(self.current_user, 'PersonDetail', PermissionEnum.update))
        self.detail_delete_btn.setEnabled(has_permission(self.current_user, 'PersonDetail', PermissionEnum.delete))
    
    def setup_user_session(self, user):
        self.current_user = user
        
        # تحميل الأيقونة بشكل متأخر بعد ظهور النافذة
        if not self.icon_loaded:
            from database.db import get_application_icon
            icon = get_application_icon()
            if icon:
                self.setWindowIcon(icon)
            self.icon_loaded = True
        
        self.setup_user_profile()
        self.check_permissions()

    def setup_user_profile(self):
        if self.current_user:
            if hasattr(self, 'welcome_msg'):
                self.welcome_msg.setText(f"مرحباً {self.current_user.name} 👋")
            if hasattr(self, 'username_label'):
                self.username_label.setText(f"@{self.current_user.username}")
    
    # === Global Funcation ===
    def _create_readonly_item(self, text):
        """دالة مساعدة لإنشاء عنصر للقراءة فقط"""
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    # ==== QListWidget ====
    def disable_item(self, item):
        # إزالة flag التمكين باستخدام ~ (NOT) و & (AND)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)

    def enable_item(self, item):
        # إضافة flag التمكين باستخدام | (OR)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)

    def set_sellected_list_item(self, list_widget: QListWidget, item_id: int):
        """Set the selected item in a QListWidget by its index."""
        item = list_widget.item(item_id)
        if item:
            list_widget.setCurrentItem(item)

    # ===== Tab Router =====
    def init_tab_router(self):
        self.tab_router = {
            PersonType.ORPHAN: {
                0: self.load_orphan_tab,
                1: self.load_balance_tab,
                2: self.load_transactions_tab,
            },
            PersonType.DECEASED: {
                3: self.load_deceased_tab,
                4: self.load_balance_tab,
                5: self.load_deceased_transaction_tab,
                6: self.load_deceased_orphans_tab,
            },
            PersonType.GUARDIAN: {
                7: self.load_guardian_tab,
                8: self.load_balance_tab,
                9: self.load_guardian_transactions_tab,
                10: self.load_guardian_orphans_tab,
            },
        }

    # ===== Main Tab Changed =====
    def on_main_tab_changed(self, index):
        self.disable_item(self.listWidget.item(1)) # Disable Person Record tab initially
        if index == 0:
            self.setup_user_profile()
            self.init_dashboard()
        elif index == 1:
            self.on_tab_changed(self.person_record_tabs.currentIndex())
        elif index == 2:
            self.controller = PersonController(self.db_service)
        elif index == 3:
            self.load_table_paginated(
                self.deceased_people_table,
                self.deceased_pagination,
                self.pagination_label,
                self.db_service.get_deceased_people_paginated,
                self.render_deceased_row
            )

        elif index == 4:
            self.load_table_paginated(
                self.guardians_table,
                self.guardians_pagination,
                self.pagination_label_2,
                self.db_service.get_guardians_paginated,
                self.render_guardian_row
            )
        elif index == 5:
            self.load_table_paginated(
                self.orphans_table,
                self.orphans_pagination,
                self.pagination_label_3,
                self.db_service.get_orphans_paginated,
                self.render_orphan_row
            )
        elif index == 6:
            self.load_table_paginated(
                self.orphans_older_or_equal_18_table,
                self.orphans_older_or_equal_18_pagination,
                self.pagination_label_4,
                self.db_service.get_orphans_older_than_or_equal_18_paginated,
                self.render_orphan_older_equal_18_row
            )
        elif index == 7:
            self.load_users_list()
            self.load_roles_combo(self.role_comboBox)
            self.load_roles_combo(self.role_comboBox_2)
        elif index == 8:
            self.load_roles()
        elif index == 9:
            self.load_roles_combo(self.roles_combo)
        elif index == 10:
            self.load_table_paginated(
                self.activity_logs_table,
                self.activity_log_pagination,
                self.pagination_label_5,
                self.db_service.get_activity_logs_paginated,
                self.render_activity_log_row,
            )
            # self.load_activity_log_list()

    # ===== Configure Tabs =====
    def configure_tabs(self, person_type):
        orphan_tabs = [0, 1, 2]
        deceased_tabs = [3, 4, 5, 6]
        guardian_tabs = [7, 8, 9, 10]
        all_tabs = orphan_tabs + deceased_tabs + guardian_tabs

        # إخفاء الجميع
        for i in all_tabs:
            self.person_record_tabs.setTabVisible(i, False)

        # إظهار المجموعات وتحديد التاب الافتراضي
        if person_type == PersonType.ORPHAN:
            for i in orphan_tabs: self.person_record_tabs.setTabVisible(i, True)
            self.person_record_tabs.setCurrentIndex(0)
        elif person_type == PersonType.DECEASED:
            for i in deceased_tabs: self.person_record_tabs.setTabVisible(i, True)
            self.person_record_tabs.setCurrentIndex(3)
        elif person_type == PersonType.GUARDIAN:
            for i in guardian_tabs: self.person_record_tabs.setTabVisible(i, True)
            self.person_record_tabs.setCurrentIndex(7)

        # إجبار النظام على تحميل بيانات التاب النشط فوراً
        self.on_tab_changed(self.person_record_tabs.currentIndex())

    # ===== Tab Changed Handler =====
    def on_tab_changed(self, index):
        # الحصول على الشخص والنوع من الكنترولر
        person, ptype = self.controller.get()
        if not person:
            return

        # اختيار الدالة المناسبة من الـ router
        loader = self.tab_router.get(ptype, {}).get(index)
        
        if loader:
            # نصيحة: يفضل عمل refresh للكائن لضمان جلب آخر التحديثات من DB
            try:
                self.db_service.session.refresh(person)
            except:
                pass # في حال كان الكائن جديداً ولم يُحفظ بعد
                
            loader() # استدعاء دالة التحميل (مثلاً load_deceased_tab)

    def on_users_tabs_changed(self, index):
        if index == 0:
            self.load_users_list()

    def on_add_person_record_tabs_changed(self, index):
        today = datetime.now().strftime('%d/%m/%Y')
        if index == 0:
            self.add_guardian_start_date.setText(today)
        elif index == 1:
            self.add_guardian_start_date_2.setText(today)
        elif index == 2:
            self.add_guardian_start_date_3.setText(today)

    # ===== Search =====
    def get_table_headers(self, table):
        headers = {}
        for i in range(table.columnCount()):
            header_text = table.horizontalHeaderItem(i).text().strip()
            headers[header_text] = i
        return headers

    def fill_form_data(self, person, fields_map):
        """
        تعبئة الحقول بشكل ديناميكي بناءً على البيانات المتوفرة في كائن الشخص.
        """
        if not person:
            return

        # 1. الحقول الأساسية (الاسم ورقم الهوية)
        if 'id' in fields_map:
            fields_map['id'].setText(str(person.id))
        if 'name' in fields_map:
            fields_map['name'].setText(person.name or "")
        if 'national_id' in fields_map:
            fields_map['national_id'].setText(person.national_id or "")

        # 2. حقول المتوفى الإضافية
        if 'date_death' in fields_map and hasattr(person, 'date_death'):
            if person.date_death:
                d = person.date_death
                fields_map['date_death'].setText(d.strftime("%d/%m/%Y"))

        if 'account_number' in fields_map and hasattr(person, 'account_number'):
            fields_map['account_number'].setText(person.account_number or "")

        if 'archives_number' in fields_map and hasattr(person, 'archives_number'):
            fields_map['archives_number'].setText(person.archives_number or "")

        # 3. حقول الوصي (رقم الجوال)
        if 'phone' in fields_map and hasattr(person, 'phone'):
            fields_map['phone'].setText(person.phone or "")

    def execute_person_search(self, search_dialog_class, fields_map, field_one=None, field_two=None):
        """
        تنفيذ عملية البحث وتعبئة الحقول الممررة فقط.
        :param search_dialog_class: كلاس النافذة (GuardianSearchDialog أو DeceasedSearchDialog)
        :param fields_map: قاموس يربط مسميات البيانات بالحقول المراد تعبئتها
        """
        # 1. إنشاء النافذة المطلوبة
        dialog = search_dialog_class(self.db_service, self)
        
        # 2. إذا تم اختيار شخص
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.selected_person:
                # 3. استدعاء دالة التعبئة وتمرير الخريطة الخاصة بهذا الزر تحديداً
                self.fill_form_data(dialog.selected_person, fields_map)
                if field_one:
                    field_one.clear()
                if field_two:
                    field_two.setText(datetime.now().strftime('%d/%m/%Y'))

    def prompt_select_person(self, results: list):
        """Show a dialog to let user pick one result from the list.
        `results` is a list of tuples (obj, person_type).
        Returns (obj, person_type) or None.
        """
        items = []
        mapping = {}
        for idx, (obj, ptype) in enumerate(results, start=1):
            label = None
            if ptype == PersonType.ORPHAN:
                label = f"{idx}. يتيم — {obj.name} ({obj.national_id or 'بدون هوية'})"
            elif ptype == PersonType.GUARDIAN:
                label = f"{idx}. وصي — {obj.name} ({obj.national_id or 'بدون هوية'})"
            else:
                label = f"{idx}. متوفى — {obj.name} ({obj.national_id or 'بدون هوية'})"
            items.append(label)
            mapping[label] = (obj, ptype)

        item, ok = QInputDialog.getItem(self, "اختيار نتيجة", "النتائج المتطابقة:", items, 0, False)
        if ok and item:
            return mapping.get(item)
        return None

    def search_by_id_or_name(self):
        term = self.search_input.text().strip()

        if not term:
            QMessageBox.warning(self, "خطأ", "الرجاء إدخال رقم الهوية، الاسم أو رقم الأرشيف")
            return

        db = self.db_service.session
        results = []

        # 1. محاولة البحث عن مطابقة تامة (هوية أو أرشيف)
        orphan, guardian, deceased_id, deceased_arc = self.db_service.find_by_archive_or_id(term)
        
        if orphan: results.append((orphan, PersonType.ORPHAN))
        if guardian: results.append((guardian, PersonType.GUARDIAN))
        if deceased_id: results.append((deceased_id, PersonType.DECEASED))
        
        # إضافة نتيجة الأرشيف إذا كانت مختلفة عن نتيجة الهوية (تجنب التكرار)
        if deceased_arc and deceased_arc not in [r[0] for r in results]:
            results.append((deceased_arc, PersonType.DECEASED))

        # 2. إذا لم توجد نتائج مطابقة تماماً، نبحث بالاسم (Partial Search)
        if not results:
            tokens = [t.strip() for t in term.split() if t.strip()]
            if tokens:
                def name_filters(model):
                    return [model.name.ilike(f"%{t}%") for t in tokens]

                orphans = db.query(Orphan).filter(*name_filters(Orphan)).all()
                guardians = db.query(Guardian).filter(*name_filters(Guardian)).all()
                deceaseds = db.query(Deceased).filter(*name_filters(Deceased)).all()

                results += [(o, PersonType.ORPHAN) for o in orphans]
                results += [(g, PersonType.GUARDIAN) for g in guardians]
                results += [(d, PersonType.DECEASED) for d in deceaseds]

        # 3. معالجة عرض النتائج
        if not results:
            QMessageBox.information(self, "بحث", "لا يوجد نتائج مطابقة")
            return

        # إذا كانت نتيجة واحدة فقط، افتحها مباشرة
        if len(results) == 1:
            obj, ptype = results[0]
            self.open_person(obj, ptype)
            self.enable_item(self.listWidget.item(1))
            self.set_sellected_list_item(self.listWidget, 1)
            return

        # إذا تعددت النتائج، اطلب من المستخدم الاختيار
        choice = self.prompt_select_person(results)
        if choice:
            obj, ptype = choice
            self.open_person(obj, ptype)
            self.enable_item(self.listWidget.item(1))
            self.set_sellected_list_item(self.listWidget, 1)

    def search_deceased_by_id_or_name(self):
        self.execute_person_search(DeceasedSearchDialog, {
            'id': self.lineEdit_38,
            'name': self.add_deceased_name_2,
            'national_id': self.add_deceased_id_2,
            'account_number': self.add_deceased_account_number_2,
            'archives_number': self.add_deceased_archives_number_2,
            'date_death': self.add_deceased_date_death_2,
        })

    def search_deceased_by_id_or_name_2(self):
        self.execute_person_search(DeceasedSearchDialog, {
            'id': self.lineEdit_40,
            'name': self.detail_deceased_name,
            'national_id': self.detail_deceased_id,
            'account_number': self.detail_deceased_account_number,
            'archives_number': self.detail_deceased_archives_number,
            'date_death': self.detail_deceased_date_death,
        })

    def search_guardian_by_id_or_name(self):
        self.execute_person_search(GuardianSearchDialog, {
            'id': self.lineEdit_37,
            'name': self.add_guardian_name,
            'national_id': self.add_guardian_id,
            'phone': self.add_guardian_phone
        })

    def search_guardian_by_id_or_name_2(self):
        self.execute_person_search(GuardianSearchDialog, {
            'id': self.lineEdit_39,
            'name': self.add_guardian_name_2,
            'national_id': self.add_guardian_id_2,
            'phone': self.add_guardian_phone_2
        })

    def search_guardian_by_id_or_name_3(self):
        self.execute_person_search(
            GuardianSearchDialog, {
                'name': self.detail_guardian_name_2,
                'national_id': self.detail_guardian_id_2,
                'phone': self.detail_guardian_phone_2
            },
            self.detail_guardian_kinship_2,
            self.detail_guardian_start_date_2
        )

    def search_guardian_by_id_or_name_4(self):
        self.execute_person_search(
            GuardianSearchDialog, {
                'id': self.lineEdit_41,
                'name': self.detail_guardian_name,
                'national_id': self.detail_guardian_id,
                'phone': self.detail_guardian_phone
            },
            self.detail_guardian_kinship,
            self.detail_guardian_start_date
        )

    def search_orphan_by_id_or_name(self, table: QTableWidget, file_type: str = ''):
        # منع تكرار اليتيم في الجدول
        existing_ids = [int(table.item(r, 0).text()) for r in range(table.rowCount()) 
                        if table.item(r, 0) and table.item(r, 0).text().isdigit()]

        dialog = OrphanSearchDialog(self.db_service, self, file_type=file_type, exclude_ids=existing_ids)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            o = dialog.selected_orphan
            row_idx = table.rowCount()
            table.insertRow(row_idx)
            headers = self.get_table_headers(table) # دالة جلب أسماء الأعمدة
            
            # جلب بيانات الوصي الأساسي
            primary_link = next((l for l in o.guardian_links if l.is_primary), None)

            # --- توزيع البيانات حسب الأعمدة المتاحة في الواجهة ---
            
            # 1. بيانات الهوية والاسم
            mapping = {"ID": str(o.id), "الإسم": o.name, "رقم الهوية": o.national_id}
            for key, val in mapping.items():
                if key in headers:
                    table.setItem(row_idx, headers[key], self._create_readonly_item(val))

            # 2. بيانات الوصي
            if primary_link and primary_link.guardian:
                g_map = {
                    "الوصي الأساسي": primary_link.guardian.name,
                    "هوية الوصي": primary_link.guardian.national_id,
                    "صلة القرابة": primary_link.relation or '-'
                }
                
                for key, val in g_map.items():
                    if key in headers:
                        item = self._create_readonly_item(val)                        
                        table.setItem(row_idx, headers[key], item)

            # 3. حقل الجنس (ComboBox المعطل)
            if "الجنس" in headers:
                combo = QComboBox()
                combo.addItems(["اختر", "ذكر", "أنثى"])
                idx = o.gender.value if hasattr(o.gender, 'value') else int(o.gender)
                combo.setCurrentIndex(idx)
                combo.setEnabled(False)
                # إضافة ستايل لجعل اللون واضحاً رغم التعطيل (اختياري)
                # combo.setStyleSheet("QComboBox { color: black; background: #f0f0f0; }")
                table.setCellWidget(row_idx, headers["الجنس"], combo)

            # 4. الأرصدة والتواريخ
            if "تاريخ الميلاد" in headers:
                dob = o.date_birth.strftime("%d/%m/%Y") if o.date_birth else ""
                table.setItem(row_idx, headers["تاريخ الميلاد"], self._create_readonly_item(dob))

            cur_map = {
                "رصيد الشيكل": "ILS", 
                "رصيد الدولار": "USD", 
                "رصيد الدينار": "JOD", 
                "رصيد اليورو": "EUR"
            }

            # جلب الأرصدة الموجودة فعلياً
            balances = {b.currency.code: b.balance for b in o.balances}
            for col_name, code in cur_map.items():
                col_idx = headers.get(col_name)
                if col_idx is not None:
                    raw_val = balances.get(code, 0)
                    display_text = f"{raw_val:,.2f}"
                    item = self._create_readonly_item(display_text)
                    table.setItem(row_idx, col_idx, item)

    def search_orphan_by_id_or_name_2(self, table: QTableWidget, file_type: str = ''):
        # منع تكرار اليتيم في الجدول
        existing_ids = [int(table.item(r, 0).text()) for r in range(table.rowCount()) 
                        if table.item(r, 0) and table.item(r, 0).text().isdigit()]

        dialog = OrphanSearchDialog(self.db_service, self, file_type=file_type, exclude_ids=existing_ids)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            o = dialog.selected_orphan
            row_idx = table.rowCount()
            table.insertRow(row_idx)
            table.setItem(row_idx, 0, self._create_readonly_item(str(o.id)))         
            table.setItem(row_idx, 1, self._create_readonly_item(o.name))         
            table.setItem(row_idx, 2, self._create_readonly_item(o.national_id))         
            table.setItem(row_idx, 3, self._create_readonly_item(o.date_birth.strftime("%d/%m/%Y") if o.date_birth else ""))
            combo = QComboBox()
            combo.addItems(["اختر", "ذكر", "أنثى"])
            idx = o.gender.value if hasattr(o.gender, 'value') else int(o.gender)
            combo.setCurrentIndex(idx)
            combo.setEnabled(False)
            table.setCellWidget(row_idx, 4, combo)         
            # جلب بيانات الوصي الأساسي
            # primary_link = next((l for l in o.guardian_links if l.is_primary), None)
            check_widget = QWidget()
            check_layout = QHBoxLayout(check_widget)
            checkBox = QCheckBox()
            check_layout.addWidget(checkBox)
            check_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            check_layout.setContentsMargins(0, 0, 0, 0)
            checkBox.setChecked(True)
            table.setCellWidget(row_idx, 5, check_widget)
            table.setItem(row_idx, 6, QTableWidgetItem(""))   
            table.setItem(row_idx, 7, QTableWidgetItem(date.today().strftime("%d/%m/%Y")))   
            table.setItem(row_idx, 8, self._create_readonly_item(""))
            
            # جلب الأرصدة الموجودة فعلياً
            balances = {b.currency.code: b.balance for b in o.balances}
            table.setItem(row_idx, 9, self._create_readonly_item(f"{balances.get('ILS', 0):,.2f}"))
            table.setItem(row_idx, 10, self._create_readonly_item(f"{balances.get('USD', 0):,.2f}"))
            table.setItem(row_idx, 11, self._create_readonly_item(f"{balances.get('JOD', 0):,.2f}"))
            table.setItem(row_idx, 12, self._create_readonly_item(f"{balances.get('EUR', 0):,.2f}"))

    # ===== Open Person Methods =====
    def open_person(self, obj, person_type):
        # تحقق إذا كان الكائن فارغاً قبل البدء
        if obj is None:
            QMessageBox.warning(self, "خطأ", "لا يمكن عرض البيانات: السجل غير موجود.")
            return
        
        self.controller.set_person(obj, person_type)
        self.configure_tabs(person_type)
        self.load_card(obj, person_type)
        self.tabWidget.setCurrentIndex(1)
        # Load first visible tab
        self.on_tab_changed(self.person_record_tabs.currentIndex())

    def open_guardian_from_deceased(self):
        d = self.controller.current_person
        if not d:
            return

        guardian = self.get_guardian_from_deceased(d)
        if not guardian:
            QMessageBox.warning(self, "تنبيه", "لا يوجد وصي مرتبط بالمتوفّي")
            return

        self.open_person(guardian, PersonType.GUARDIAN)

    def get_guardian_from_deceased(self, deceased):
        if not deceased.orphans:
            return None

        for orphan in deceased.orphans:
            if orphan.guardian_links:
                primary = next(
                    (l.guardian for l in orphan.guardian_links if l.is_primary),
                    orphan.guardian_links[0].guardian
                )
                return primary

        return None

    def open_primary_guardian_from_orphan(self):
        o = self.controller.current_person
        if not o:
            return

        guardian = self.get_primary_guardian(o)
        if not guardian:
            QMessageBox.warning(self, "تنبيه", "لا يوجد وصي مرتبط")
            return

        self.open_person(guardian, PersonType.GUARDIAN)

    def get_primary_guardian(self, orphan):
        if not orphan.guardian_links:
            return None
        return next(
            (link.guardian for link in orphan.guardian_links if link.is_primary),
            None
        )

    # ==== QTableWidget Methods === 
    def add_row_to_orphans_table(self, table: QTableWidget, edit_mode=True):
        current_row_count = table.rowCount()
        table.insertRow(current_row_count)
        
        headers = self.get_table_headers(table) 
        
        # 1. تهيئة أولية لجميع الخلايا
        for col_idx in range(table.columnCount()):
            if 'ID' in headers:
                table.setItem(current_row_count, headers['ID'], self._create_readonly_item(""))
            else:
                table.setItem(current_row_count, col_idx, QTableWidgetItem(""))

        # 2. حقل الجنس
        if "الجنس" in headers:
            col_idx = headers["الجنس"]
            combo = QComboBox()
            combo.addItems(["اختر", "ذكر", "أنثى"])
            table.setCellWidget(current_row_count, col_idx, combo)
        
        # 3. حقول الوصاية (التصحيح هنا)
        guardian_columns = ["الوصي الأساسي", "هوية الوصي", "صلة القرابة"]
        for col_name in guardian_columns:
            if col_name in headers:
                item = QTableWidgetItem("")
                
                # نقارن col_name (النص) وليس رقم العمود
                # if col_name  == "الوصي الأساسي":
                #     # منع التعديل اليدوي - يجب جلبهم عبر البحث عن الهوية أو اختيار محدد
                #     item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                
                table.setItem(current_row_count, headers[col_name], item)

        for col_name in ["بدء الوصاية",  "وصي أساسي", "انتهاء الوصاية"]:
            if col_name in headers:
                if col_name == "وصي أساسي":
                    check_widget = QWidget()
                    check_layout = QHBoxLayout(check_widget)
                    checkBox = QCheckBox()
                    check_layout.addWidget(checkBox)
                    check_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    check_layout.setContentsMargins(0, 0, 0, 0)
                    checkBox.setChecked(True)
                    table.setCellWidget(current_row_count, headers[col_name], check_widget)
                elif col_name == "بدء الوصاية":
                    table.setItem(current_row_count, headers[col_name], QTableWidgetItem(date.today().strftime("%d/%m/%Y")))  
                else:
                    table.setItem(current_row_count, headers[col_name], self._create_readonly_item(""))

        # # 4. أرصدة العملات
        # currency_cols = ["رصيد الشيكل", "رصيد الدولار", "رصيد الدينار", "رصيد اليورو"]
        # for col_name in currency_cols:
        #     if col_name in headers:
        #         item = QTableWidgetItem("")
        #         table.setItem(current_row_count, headers[col_name], item)
        
        # 4. أرصدة العملات
        currency_cols = ["رصيد الشيكل", "رصيد الدولار", "رصيد الدينار", "رصيد اليورو"]
        
        # جلب النص المختار من مجموعة الأزرار (بالتساوي، يدوي، إلخ)
        selected_mode = self.buttonGroup.checkedButton().text()
        can_edit_balance = (selected_mode == "يدوي")

        for col_name in currency_cols:
            if col_name in headers:
                # إنشاء الخلية بقيمة افتراضية "0"
                item = QTableWidgetItem("0")
                if not edit_mode:
                    if can_edit_balance:
                        # مسموح التعديل: خلفية بيضاء وخصائص كاملة
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                        item.setBackground(QColor("white"))
                    else:
                        # غير مسموح: خلفية رمادية وقراءة فقط
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        item.setBackground(QColor("#f0f0f0")) 
                        # item.setForeground(QColor("#7d7d7d")) # لون نص باهت
                else:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(QColor("white"))

                table.setItem(current_row_count, headers[col_name], item)

    def remove_selected_orphan_row(self, table: QTableWidget):
        row = table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد صف")
            return

        # 1. جلب الـ ID للتأكد إذا كان السجل مخزناً في القاعدة أم مجرد إضافة مؤقتة
        id_item = table.item(row, 0)
        
        # إذا كان الصف جديداً (لا يوجد ID) أو الخلية فارغة، احذفه من الواجهة فوراً
        if not id_item or not id_item.text().strip() or not id_item.text().isdigit():
            table.removeRow(row)
            return

        orphan_id = int(id_item.text())
        
        # 2. التحقق من وجود الشخص الحالي (متوفى أو وصي)
        # إذا لم يكن هناك شخص محدد (حالة إضافة ملف جديد تماماً)، نحذف من الواجهة فقط
        if not hasattr(self.controller, 'current_person') or self.controller.current_person is None:
            table.removeRow(row)
            return

        db = self.db_service.session
        orphan = db.query(Orphan).get(orphan_id) # استخدام get أسرع للـ ID

        if not orphan:
            table.removeRow(row)
            return

        # 3. معالجة الحذف الفعلي بناءً على نوع الصفحة
        # ===== الحالة 1: من صفحة الوصي → فك ارتباط فقط =====
        if self.controller.current_type == PersonType.GUARDIAN:
            guardian = self.controller.current_person
            link = db.query(OrphanGuardian).filter_by(
                orphan_id=orphan.id,
                guardian_id=guardian.id
            ).first()

            # إذا كان اليتيم في الجدول ولكن ليس له رابط في القاعدة بعد (أضيف بالبحث للتو)
            if not link:
                table.removeRow(row)
                return

            confirm = QMessageBox.question(
                self, "تأكيد فك الارتباط",
                f"هل تريد فك ارتباط اليتيم '{orphan.name}' عن الوصي '{guardian.name}'؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    db.delete(link)
                    db.commit()
                    log_activity(
                        db, self.current_user.id, ActionTypes.DELETE, ResourceTypes.ORPHAN_GUARDIAN, resource_id=link.id,
                        description=f"فك ارتباط اليتيم '{orphan.name}' عن الوصي '{guardian.name}'"
                    )
                    table.removeRow(row)
                    QMessageBox.information(self, "تم", "تم فك الارتباط بنجاح")
                except Exception as e:
                    db.rollback()
                    QMessageBox.warning(self, "خطأ", f"فشل فك الارتباط: {str(e)}")

        # ===== الحالة 2: من صفحة المتوفّي → فك ارتباط اليتيم بدل حذفه =====
        elif self.controller.current_type == PersonType.DECEASED:
            if not orphan.deceased_id:
                table.removeRow(row)
                return
            
            # ===== التحقق من الأرصدة والحركات قبل السماح بفك الارتباط =====
            has_balances = any(bal.balance > 0 for bal in orphan.balances)
            has_transactions = len(orphan.transactions) > 0
            
            if has_balances or has_transactions:
                # تفاصيل الأرصدة والحركات
                balance_info = []
                for bal in orphan.balances:
                    if bal.balance > 0:
                        balance_info.append(f"• {bal.currency.code}: {bal.balance:,.2f}")
                
                transaction_count = len(orphan.transactions)
                
                error_msg = f"لا يمكن فك ارتباط اليتيم '{orphan.name}' عن المتوفى.\n\n"
                error_msg += "السبب:\n"
                
                if has_balances:
                    error_msg += f"➤ اليتيم يملك أرصدة مالية:\n"
                    error_msg += "\n".join(balance_info)
                    error_msg += "\n\n"
                
                if has_transactions:
                    error_msg += f"➤ اليتيم يملك {transaction_count} حركة مالية مسجلة في النظام\n\n"
                
                error_msg += "يجب تصفية هذه الأرصدة والحركات أولاً قبل فك الارتباط."
                
                QMessageBox.warning(
                    self, 
                    "لا يمكن فك الارتباط",
                    error_msg
                )
                return
            
            # إذا لم تكن هناك أرصدة أو حركات، يتم السماح بفك الارتباط
            confirm = QMessageBox.question(
                self, "تأكيد فك ارتباط",
                f"هل تريد فك ارتباط اليتيم '{orphan.name}' عن ملف المتوفى الحالي؟\n"
                "ملاحظة: اليتيم سيبقى في النظام كيتيم غير مرتبط.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    # بدل حذف الكائن (db.delete)، نقوم بتعديل الحقل فقط
                    deceased_name = orphan.deceased.name
                    orphan.deceased_id = None 
                    
                    db.commit()
                    log_activity(
                        db, self.current_user.id, ActionTypes.UPDATE, ResourceTypes.ORPHAN, resource_id=orphan.id,
                        description=f"فك ارتباط اليتيم '{orphan.name}' عن ملف المتوفى '{deceased_name}'"
                    )
                    table.removeRow(row)
                    QMessageBox.information(self, "تم", "تم فك ارتباط اليتيم بنجاح")
                except Exception as e:
                    db.rollback()
                    QMessageBox.warning(self, "خطأ", f"فشل فك الارتباط: {str(e)}")

    def _get_widget_or_text(self, table, row, col):
        widget = table.cellWidget(row, col)
        if widget and isinstance(widget, QComboBox):
            return widget.currentText().strip()
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def get_orphans_table_data(self, table_widget: QTableWidget, require_at_least_one: bool = True):
        """
        قراءة بيانات الأيتام بديناميكية كاملة.
        تدعم غياب أعمدة (صلة القرابة، بدء الوصاية، انتهاء الوصاية) من الواجهة.
        """
        orphans_data = []
        table = table_widget
        
        # 1. بناء خريطة الأعمدة المتوفرة في الواجهة حالياً
        column_map = {}
        for col in range(table.columnCount()):
            header = table.horizontalHeaderItem(col)
            if header:
                column_map[header.text().strip()] = col

        for row in range(table.rowCount()):
            try:
                def get_val(header_name):
                    col = column_map.get(header_name)
                    if col is None: return None # العمود غير موجود في الواجهة أصلاً
                    item = table.item(row, col)
                    return item.text().strip() if item else ""

                # --- أ. البيانات الأساسية (يجب أن تتوفر في أي واجهة) ---
                name = get_val("الإسم")
                if not name:
                    if any(get_val(h) for h in column_map if h != "الإسم"):
                        raise ValueError(f"يرجى إدخال اسم اليتيم في الصف {row+1}")
                    continue

                nid = get_val("رقم الهوية")
                if nid and (not nid.isdigit() or len(nid) != 9):
                    raise ValueError(f"رقم الهوية لـ '{name}' غير صحيح (9 أرقام).")

                dob_text = get_val("تاريخ الميلاد")
                # if not dob_text:
                #     raise ValueError(f'يرجى إدخال تاريخ ميلاد اليتيم في الصف {row+1}')
                dob_date = parse_and_validate_date(dob_text)

                # --- ب. التعامل الذكي مع الحقول التي قد تكون مفقودة ---

                # صلة القرابة: إجبارية فقط "إذا كان العمود موجوداً" في الجدول
                kinship = get_val("صلة القرابة")
                if "صلة القرابة" in column_map: # العمود موجود في الواجهة
                    if not kinship or kinship == "غير محدد":
                        raise ValueError(f"حقل صلة القرابة إجباري لليتيم '{name}'")
                else:
                    kinship = "غير محدد" # قيمة افتراضية في حال غياب العمود تماماً
                
                guardian_national_id = None
                if 'هوية الوصي' in column_map:
                    guardian_national_id = get_val("هوية الوصي")
                
                guardian_name = None
                if 'الوصي الأساسي' in column_map:
                    guardian_name = get_val('الوصي الأساسي')
                
                # بدء الوصاية: قراءة فقط إذا وجد العمود
                start_date = None
                start_date_text = get_val("بدء الوصاية")
                if start_date_text:
                    try:
                        start_date = parse_and_validate_date(start_date_text)
                    except:
                        raise ValueError(f"تاريخ بدء وصاية '{name}' غير صحيح")

                # --- ج. الأرصدة (ترجع كحقول منفصلة) ---
                def parse_balance(header_name):
                    val = get_val(header_name)
                    if val is None: return Decimal(0)
                    try:
                        clean_val = val.replace(',', '')
                        return Decimal(clean_val) if clean_val else Decimal(0)
                    except: return Decimal(0)
                
                is_primary = None
                if "وصي أساسي" in column_map:
                    widget = table.cellWidget(row, column_map["وصي أساسي"])
                    if widget and isinstance(widget, QWidget):
                        checkbox = widget.findChild(QCheckBox)
                        if checkbox:
                            is_primary = checkbox.isChecked()

                # تجميع القاموس بالهيكل المطلوب
                orphan_entry = {
                    "id": int(get_val("ID")) if get_val("ID") and get_val("ID").isdigit() else None,
                    "name": name,
                    "national_id": nid,
                    "date_birth": dob_date,
                    "gender": GenderEnum(table.cellWidget(row, column_map["الجنس"]).currentIndex()) if "الجنس" in column_map else None,
                    "relation": kinship,
                    "start_date": start_date,
                    "guardian_name": guardian_name,
                    "guardian_national_id": guardian_national_id,
                    "is_primary": is_primary,
                    "ils_balance": parse_balance("رصيد الشيكل"),
                    "usd_balance": parse_balance("رصيد الدولار"),
                    "jod_balance": parse_balance("رصيد الدينار"),
                    "eur_balance": parse_balance("رصيد اليورو"),
                }
                
                orphans_data.append(orphan_entry)

            except ValueError as ve:
                raise ve
            except Exception as e:
                raise ValueError(f"خطأ في الصف {row+1}: {str(e)}")

        if not orphans_data and require_at_least_one:
            raise ValueError("يجب إضافة يتيم واحد على الأقل.")

        return orphans_data

    def get_orphan_transactions_table(self, table_widget: QTableWidget):
        transactions_data = []
        try:
            for row in range(table_widget.rowCount()):
                # 1. جلب المعرف (ID)
                id_item = table_widget.item(row, 0)
                t_id = int(id_item.text()) if id_item and id_item.text().isdigit() else None

                # 2. استخراج العملة والنوع (دعم الـ ComboBox والـ Text)
                currency_text = self._get_widget_or_text(table_widget, row, 1)
                type_text = self._get_widget_or_text(table_widget, row, 2)

                # تجاهل الصف إذا كان فارغاً تماماً (لمنع إزعاج المستخدم برسائل خطأ لصفوف لم يقصد تعبئتها)
                amount_item = table_widget.item(row, 3)
                if not amount_item or not amount_item.text().strip():
                    if not t_id: continue # صف جديد فارغ، نتجاهله
                    else: raise ValueError(f"المبلغ مفقود في حركة مسجلة مسبقاً (صف {row+1})")

                # 3. التحقق من الاختيارات
                if currency_text in ["", "اختر"]:
                    raise ValueError(f"يرجى اختيار العملة في الصف {row+1}")
                if type_text in ["", "اختر"]:
                    raise ValueError(f"يرجى اختيار نوع العملية في الصف {row+1}")

                # 4. تنظيف ومعالجة المبلغ
                amount_clean = amount_item.text().replace(',', '').strip()
                try:
                    amount_dec = parse_decimal(amount_clean) # نستخدم الدالة الموحدة لديك
                    if amount_dec <= 0: raise ValueError
                except:
                    raise ValueError(f"المبلغ في الصف {row+1} يجب أن يكون رقماً أكبر من صفر")

                # 5. جلب التاريخ والملاحظة
                date_item = table_widget.item(row, 4)
                note_item = table_widget.item(row, 5)

                payment_method_text = self._get_widget_or_text(table_widget, row, 6) if table_widget.columnCount() > 6 else ""
                document_number_text = self._get_widget_or_text(table_widget, row, 7) if table_widget.columnCount() > 7 else ""
                person_name_text = self._get_widget_or_text(table_widget, row, 8) if table_widget.columnCount() > 8 else ""
                check_number_text = self._get_widget_or_text(table_widget, row, 9) if table_widget.columnCount() > 9 else ""
                due_date_text = self._get_widget_or_text(table_widget, row, 10) if table_widget.columnCount() > 10 else ""
                bank_name_text = self._get_widget_or_text(table_widget, row, 11) if table_widget.columnCount() > 11 else ""
                reference_number_text = self._get_widget_or_text(table_widget, row, 12) if table_widget.columnCount() > 12 else ""

                due_date_text = (due_date_text or "").strip()
                if due_date_text and due_date_text != "---":
                    parsed_due_date = try_get_date(due_date_text)
                    due_date_value = parse_and_validate_date(parsed_due_date)
                else:
                    due_date_value = None

                payment_method_text = (payment_method_text or "").strip()
                if payment_method_text in ["", "---", "اختر"]:
                    payment_method_text = None

                transactions_data.append({
                    "id": t_id,
                    "currency": currency_text,
                    "type": type_text,
                    "amount": amount_dec, # نمرره كـ Decimal مباشرة للراحة
                    "date": date_item.text().strip() if date_item else "",
                    "note": note_item.text().strip() if note_item else "",
                    "payment_method": payment_method_text,
                    "document_number": (document_number_text or "").strip() or None,
                    "person_name": (person_name_text or "").strip() or None,
                    "check_number": (check_number_text or "").strip() or None,
                    "due_date": due_date_value,
                    "bank_name": (bank_name_text or "").strip() or None,
                    "reference_number": (reference_number_text or "").strip() or None,
                })
                
            return transactions_data

        except ValueError as e:
            raise e
        except Exception as e:
            print(f"Debug Error: {str(e)}") # للبرمجة فقط
            raise ValueError(f"خطأ في بيانات الصف {row+1}. تأكد من صحة المدخلات.")

    def get_guardian_transactions_table(self, table_widget: QTableWidget):
        transactions_data = []
        try:
            for row in range(table_widget.rowCount()):
                id_item = table_widget.item(row, 0)
                t_id = int(id_item.text()) if id_item and id_item.text().isdigit() else None

                date_text = self._get_widget_or_text(table_widget, row, 1)
                type_text = self._get_widget_or_text(table_widget, row, 2)
                currency_text = self._get_widget_or_text(table_widget, row, 3)
                amount_text = self._get_widget_or_text(table_widget, row, 4)
                note_text = self._get_widget_or_text(table_widget, row, 5)
                payment_method_text = self._get_widget_or_text(table_widget, row, 6) if table_widget.columnCount() > 6 else ""
                document_number_text = self._get_widget_or_text(table_widget, row, 7) if table_widget.columnCount() > 7 else ""
                person_name_text = self._get_widget_or_text(table_widget, row, 8) if table_widget.columnCount() > 8 else ""
                check_number_text = self._get_widget_or_text(table_widget, row, 9) if table_widget.columnCount() > 9 else ""
                due_date_text = self._get_widget_or_text(table_widget, row, 10) if table_widget.columnCount() > 10 else ""
                bank_name_text = self._get_widget_or_text(table_widget, row, 11) if table_widget.columnCount() > 11 else ""
                reference_number_text = self._get_widget_or_text(table_widget, row, 12) if table_widget.columnCount() > 12 else ""

                is_empty_row = not any([
                    date_text.strip(),
                    type_text.strip() if type_text != "اختر" else "",
                    currency_text.strip() if currency_text != "اختر" else "",
                    amount_text.strip(),
                    note_text.strip(),
                    payment_method_text.strip(),
                    document_number_text.strip(),
                    person_name_text.strip(),
                    check_number_text.strip(),
                    due_date_text.strip(),
                    bank_name_text.strip(),
                    reference_number_text.strip(),
                ])
                if is_empty_row and not t_id:
                    continue

                if not date_text:
                    raise ValueError(f"يرجى إدخال تاريخ الحركة في الصف {row+1}")
                parse_and_validate_date(date_text)

                if type_text in ["", "اختر"]:
                    raise ValueError(f"يرجى اختيار نوع الحركة في الصف {row+1}")
                if currency_text in ["", "اختر"]:
                    raise ValueError(f"يرجى اختيار العملة في الصف {row+1}")

                if not amount_text:
                    raise ValueError(f"يرجى إدخال المبلغ في الصف {row+1}")

                amount_clean = amount_text.replace(',', '').strip()
                try:
                    amount_dec = parse_decimal(amount_clean)
                    if amount_dec <= 0:
                        raise ValueError
                except:
                    raise ValueError(f"المبلغ في الصف {row+1} يجب أن يكون رقماً أكبر من صفر")

                due_date_text = (due_date_text or "").strip()
                if due_date_text and due_date_text != "---":
                    parsed_due_date = try_get_date(due_date_text)
                    due_date_value = parse_and_validate_date(parsed_due_date)
                else:
                    due_date_value = None

                payment_method_text = (payment_method_text or "").strip()
                if payment_method_text in ["", "---", "اختر"]:
                    payment_method_text = None

                transactions_data.append({
                    "id": t_id,
                    "date": date_text,
                    "type": type_text,
                    "currency": currency_text,
                    "amount": amount_dec,
                    "note": note_text.strip(),
                    "payment_method": payment_method_text,
                    "document_number": (document_number_text or "").strip() or None,
                    "person_name": (person_name_text or "").strip() or None,
                    "check_number": (check_number_text or "").strip() or None,
                    "due_date": due_date_value,
                    "bank_name": (bank_name_text or "").strip() or None,
                    "reference_number": (reference_number_text or "").strip() or None,
                })

            return transactions_data
        except ValueError as e:
            raise e
        except Exception as e:
            print(f"Guardian table parse error: {str(e)}")
            raise ValueError(f"خطأ في بيانات الصف {row+1}. تأكد من صحة المدخلات.")

    def get_deceased_transactions_table(self, table_widget: QTableWidget):
        transactions_data = []
        try:
            for row in range(table_widget.rowCount()):
                id_item = table_widget.item(row, 0)
                t_id = int(id_item.text()) if id_item and id_item.text().isdigit() else None

                currency_text = self._get_widget_or_text(table_widget, row, 1)
                type_text = self._get_widget_or_text(table_widget, row, 2)
                amount_text = self._get_widget_or_text(table_widget, row, 3)
                payment_method_text = self._get_widget_or_text(table_widget, row, 4)
                receipt_number_text = self._get_widget_or_text(table_widget, row, 5)
                payer_name_text = self._get_widget_or_text(table_widget, row, 6)
                bank_name_text = self._get_widget_or_text(table_widget, row, 7)
                check_number_text = self._get_widget_or_text(table_widget, row, 8)
                due_date_text = self._get_widget_or_text(table_widget, row, 9)
                reference_number_text = self._get_widget_or_text(table_widget, row, 10)
                date_text = self._get_widget_or_text(table_widget, row, 11)
                note_text = self._get_widget_or_text(table_widget, row, 12)

                is_empty_row = not any([
                    currency_text.strip() if currency_text != "اختر" else "",
                    type_text.strip() if type_text != "اختر" else "",
                    amount_text.strip(),
                    payment_method_text.strip() if payment_method_text != "اختر" else "",
                    receipt_number_text.strip(),
                    payer_name_text.strip(),
                    bank_name_text.strip(),
                    check_number_text.strip(),
                    due_date_text.strip(),
                    reference_number_text.strip(),
                    date_text.strip(),
                    note_text.strip(),
                ])
                if is_empty_row and not t_id:
                    continue

                if currency_text in ["", "اختر"]:
                    raise ValueError(f"يرجى اختيار العملة في الصف {row+1}")
                if type_text in ["", "اختر"]:
                    raise ValueError(f"يرجى اختيار نوع الحركة في الصف {row+1}")
                if not amount_text:
                    raise ValueError(f"يرجى إدخال المبلغ في الصف {row+1}")
                if not date_text:
                    raise ValueError(f"يرجى إدخال تاريخ الحركة في الصف {row+1}")

                amount_clean = amount_text.replace(',', '').strip()
                try:
                    amount_dec = parse_decimal(amount_clean)
                    if amount_dec <= 0:
                        raise ValueError
                except:
                    raise ValueError(f"المبلغ في الصف {row+1} يجب أن يكون رقماً أكبر من صفر")

                created_date = parse_and_validate_date(date_text)

                due_date_text = (due_date_text or "").strip()
                if due_date_text and due_date_text != "---":
                    parsed_due_date = try_get_date(due_date_text)
                    due_date_value = parse_and_validate_date(parsed_due_date)
                else:
                    due_date_value = None

                payment_method_text = (payment_method_text or "").strip()
                if payment_method_text in ["", "---", "اختر"]:
                    payment_method_text = None

                transactions_data.append({
                    "id": t_id,
                    "currency": currency_text,
                    "type": type_text,
                    "amount": amount_dec,
                    "payment_method": payment_method_text,
                    "receipt_number": (receipt_number_text or "").strip() or None,
                    "payer_name": (payer_name_text or "").strip() or None,
                    "bank_name": (bank_name_text or "").strip() or None,
                    "check_number": (check_number_text or "").strip() or None,
                    "due_date": due_date_value,
                    "reference_number": (reference_number_text or "").strip() or None,
                    "created_date": created_date,
                    "note": (note_text or "").strip() or None,
                })

            return transactions_data
        except ValueError as e:
            raise e
        except Exception as e:
            print(f"Deceased table parse error: {str(e)}")
            raise ValueError(f"خطأ في بيانات الصف {row+1}. تأكد من صحة المدخلات.")

    def add_row_transaction_table(self, table: QTableWidget):
        if table is self.detail_orphan_transactions_table:
            table.setColumnCount(13)
            table.setHorizontalHeaderLabels([
                "ID", "العملة", "نوع الحركة", "المبلغ", "تاريخ الحركة", "ملاحظة",
                "طريقة الدفع", "رقم سند القبض/الصرف", "المودع/المستفيد", "رقم الشيك",
                "تاريخ الاستحقاق", "اسم البنك", "رقم المرجع/الحوالة",
            ])
            table.setColumnHidden(0, True)

        current_row_count = table.rowCount()
        table.insertRow(current_row_count)
        table.setItem(current_row_count, 0, self._create_readonly_item(''))
        
        combo_currency = QComboBox()
        currencies = self.db_service.get_currencies()
        combo_currency.addItems(['اختر']+[c.name for c in currencies])
        table.setCellWidget(current_row_count, 1, combo_currency)
        
        combo_transaction_type = QComboBox()
        combo_transaction_type.addItems(["اختر","إيداع", "سحب"])
        table.setCellWidget(current_row_count, 2, combo_transaction_type)
        
        table.setItem(current_row_count, 3, QTableWidgetItem(""))
        today_str = datetime.now().strftime("%d/%m/%Y")
        table.setItem(current_row_count, 4, QTableWidgetItem(today_str))
        table.setItem(current_row_count, 5, QTableWidgetItem(""))
        if table.columnCount() > 6:
            for col in range(6, 13):
                table.setItem(current_row_count, col, QTableWidgetItem(""))

    def add_guardian_transaction_row(self):
        table = self.transactions_table_3
        table.setColumnCount(13)
        table.setHorizontalHeaderLabels([
            "ID", "تاريخ الحركة", "نوع الحركة", "العملة", "المبلغ", "ملاحظة",
            "طريقة الدفع", "رقم سند القبض/الصرف", "المودع/المستفيد", "رقم الشيك",
            "تاريخ الاستحقاق", "اسم البنك", "رقم المرجع/الحوالة",
        ])
        table.setColumnHidden(0, True)
        row = table.rowCount()
        table.insertRow(row)

        table.setItem(row, 0, self._create_readonly_item(""))
        table.setItem(row, 1, QTableWidgetItem(datetime.now().strftime("%d/%m/%Y")))

        type_combo = QComboBox()
        type_combo.addItems(["اختر", "إيداع", "سحب"])
        table.setCellWidget(row, 2, type_combo)

        currency_combo = QComboBox()
        currency_combo.addItems(["اختر"] + [c.name for c in self.db_service.get_currencies()])
        table.setCellWidget(row, 3, currency_combo)

        table.setItem(row, 4, QTableWidgetItem(""))
        table.setItem(row, 5, QTableWidgetItem(""))
        for col in range(6, 13):
            table.setItem(row, col, QTableWidgetItem(""))
    
    def remove_selected_row_transaction_table(self, table: QTableWidget):
        row = table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد صف للحذف")
            return

        db = self.db_service.session
        # جلب معرف الحركة (ID) من العمود الأول
        id_item = table.item(row, 0)
        transaction_id = int(id_item.text()) if id_item and id_item.text().isdigit() else None

        # حالة (1): الحركة مسجلة مسبقاً في قاعدة البيانات
        if transaction_id:
            reply = QMessageBox.question(
                self, "تأكيد حذف حركة مسجلة",
                "هذه الحركة مسجلة مسبقاً في النظام. حذفها سيؤدي لتعديل الرصيد نهائياً.\nهل أنت متأكد؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                try:
                    # جلب الحركة من القاعدة
                    trans_obj = db.query(Transaction).get(transaction_id)
                    if trans_obj:
                        # عكس التأثير على الرصيد قبل الحذف
                        balance_rec = db.query(OrphanBalance).filter_by(
                            orphan_id=trans_obj.orphan_id, 
                            currency_id=trans_obj.currency_id
                        ).first()

                        if trans_obj.type == TransactionTypeEnum.deposit:
                            # إذا حذفنا إيداع، نخصم من الرصيد
                            # التحقق من المنطق السالب: هل الرصيد المتبقي يسمح بخصم هذا الإيداع؟
                            if balance_rec.balance < trans_obj.amount:
                                raise ValueError("لا يمكن حذف الإيداع لأن الرصيد الحالي أقل من مبلغ الحركة (سيصبح الرصيد سالباً).")
                            balance_rec.balance -= trans_obj.amount
                        else:
                            # إذا حذفنا سحب، نعيد المبلغ للرصيد
                            balance_rec.balance += trans_obj.amount

                        # حذف الحركة نهائياً
                        db.delete(trans_obj)
                        db.commit()
                        log_activity(db, self.current_user.id, ActionTypes.DELETE, ResourceTypes.ORPHAN_TRANSACTION, resource_id=trans_obj.id, description=f"تم حذف حركة يتيم من النظام")
                        table.removeRow(row)
                        QMessageBox.information(self, "نجاح", "تم حذف الحركة وتحديث الرصيد.")
                        # تحديث الواجهة (الأرصدة العلوية)
                        self.open_person(trans_obj.orphan, PersonType.ORPHAN)
                except ValueError as ve:
                    db.rollback()
                    QMessageBox.warning(self, "فشل الحذف", str(ve))
                except Exception as e:
                    db.rollback()
                    QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء الحذف: {str(e)}")
        
        # حالة (2): الحركة جديدة (لم تُحفظ بعد)
        else:
            table.removeRow(row)

    def remove_guardian_transaction_row(self):
        table = self.transactions_table_3
        row = table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد صف للحذف")
            return

        id_item = table.item(row, 0)
        transaction_id = int(id_item.text()) if id_item and id_item.text().isdigit() else None

        if transaction_id:
            reply = QMessageBox.question(
                self,
                "تأكيد الحذف",
                "هذه الحركة محفوظة مسبقاً. حذفها سيؤثر على رصيد الوصي. هل أنت متأكد؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            db = self.db_service.session
            try:
                trans_obj = db.query(GuardianTransaction).get(transaction_id)
                guardian = self.controller.current_person
                if not trans_obj or trans_obj.guardian_id != guardian.id:
                    raise ValueError("تعذر العثور على الحركة المطلوبة")

                balance_rec = db.query(GuardianBalance).filter_by(
                    guardian_id=guardian.id,
                    currency_id=trans_obj.currency_id,
                ).first()
                if not balance_rec:
                    raise ValueError("تعذر العثور على رصيد العملة للحركة")

                if trans_obj.type == TransactionTypeEnum.deposit:
                    if balance_rec.balance < trans_obj.amount:
                        raise ValueError("لا يمكن حذف الإيداع لأن الرصيد الحالي أقل من مبلغ الحركة")
                    balance_rec.balance -= trans_obj.amount
                else:
                    balance_rec.balance += trans_obj.amount

                db.delete(trans_obj)
                db.commit()

                table.removeRow(row)
                self.load_card(guardian, PersonType.GUARDIAN)
                self.load_balance_tab()
                QMessageBox.information(self, "نجاح", "تم حذف الحركة وتحديث الرصيد")
            except ValueError as ve:
                db.rollback()
                QMessageBox.warning(self, "تنبيه", str(ve))
            except Exception as e:
                db.rollback()
                QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء الحذف: {str(e)}")
        else:
            table.removeRow(row)

    def on_deceased_row_double_clicked(self, row, column):
        try:
            # 1. جلب الـ ID من العمود الأول (العمود رقم 0)
            id_item = self.deceased_people_table.item(row, 0)
            if not id_item:
                return
            deceased_id = int(id_item.text())
            # 2. جلب كائن اليتيم من قاعدة البيانات باستخدام الـ ID
            db = self.db_service.session
            deceased = db.query(Deceased).get(deceased_id)
            if deceased:
                self.open_person(deceased, PersonType.DECEASED)
                self.enable_item(self.listWidget.item(1))
                self.set_sellected_list_item(self.listWidget, 1)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر فتح ملف المتوفي: {str(e)}")
    
    def on_guardian_row_double_clicked(self, row, column):
        try:
            # 1. جلب الـ ID من العمود الأول (العمود رقم 0)
            id_item = self.guardians_table.item(row, 0)
            if not id_item:
                return
            guardian_id = int(id_item.text())
            # 2. جلب كائن اليتيم من قاعدة البيانات باستخدام الـ ID
            db = self.db_service.session
            guardian = db.query(Guardian).get(guardian_id)
            if guardian:
                self.open_person(guardian, PersonType.GUARDIAN)
                self.enable_item(self.listWidget.item(1))
                self.set_sellected_list_item(self.listWidget, 1)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر فتح ملف الوصي: {str(e)}")
    
    def on_orphan_row_double_clicked(self, row, column, table):
        try:
            # 1. جلب الـ ID من العمود الأول (العمود رقم 0)
            id_item = table.item(row, 0)
            if not id_item:
                return
            orphan_id = int(id_item.text())
            # 2. جلب كائن اليتيم من قاعدة البيانات باستخدام الـ ID
            db = self.db_service.session
            orphan = db.query(Orphan).get(orphan_id)
            if orphan:
                self.open_person(orphan, PersonType.ORPHAN)
                self.enable_item(self.listWidget.item(1))
                self.set_sellected_list_item(self.listWidget, 1)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر فتح ملف اليتيم: {str(e)}")

    def update_table_editing_mode(self):
        table = self.add_deceased_orphans_table
        selected_button = self.buttonGroup.checkedButton().text()
        
        balance_columns = ["رصيد الشيكل", "رصيد الدولار", "رصيد الدينار", "رصيد اليورو"]
        
        column_indices = []
        for col in range(table.columnCount()):
            header = table.horizontalHeaderItem(col)
            if header and header.text().strip() in balance_columns:
                column_indices.append(col)

        # المنطق الجديد:
        for row in range(table.rowCount()):
            # الحصول على الـ ID (نفترض أنه في العمود الأول index 0)
            id_item_obj = table.item(row, 0)
            id_val = id_item_obj.text().strip() if id_item_obj else ""

            # الشرط: يسمح بالتعديل فقط إذا كان الزر "يدوي" والـ ID فارغ
            is_manual = (selected_button == "يدوي")
            has_no_id = (id_val == "") 
            
            can_edit_this_row = is_manual and has_no_id

            for col in column_indices:
                item = table.item(row, col)
                if item:
                    if can_edit_this_row:
                        # تفعيل التعديل
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled)
                        item.setBackground(QColor("white"))
                    else:
                        # تعطيل التعديل
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        # تلوين الخلية بالرمادي إذا كان هناك ID لمنع التعديل حتى لو كان الوضع "يدوي"
                        item.setBackground(QColor("#f0f0f0"))

    def add_deceased_transaction_row(self):
        table = self.detail_deceased_transactions_table
        current_row_count = table.rowCount()
        table.insertRow(current_row_count)
        table.setItem(current_row_count, 0, self._create_readonly_item(''))
        
        combo_currency = QComboBox()
        currencies = self.db_service.get_currencies()
        combo_currency.addItems(['اختر']+[c.name for c in currencies])
        table.setCellWidget(current_row_count, 1, combo_currency)
        
        combo_transaction_type = QComboBox()
        combo_transaction_type.addItems(["اختر","إيداع", "سحب"])
        table.setCellWidget(current_row_count, 2, combo_transaction_type)
        
        table.setItem(current_row_count, 3, QTableWidgetItem(""))
        
        combo_payment_method = QComboBox()
        combo_payment_method.addItems(["اختر", "نقداً", "شيك", "تحويل بنكي"])
        table.setCellWidget(current_row_count, 4, combo_payment_method)
        
        table.setItem(current_row_count, 5, QTableWidgetItem(""))
        table.setItem(current_row_count, 6, QTableWidgetItem(""))
        table.setItem(current_row_count, 7, QTableWidgetItem(""))
        table.setItem(current_row_count, 8, QTableWidgetItem(""))
        table.setItem(current_row_count, 9, QTableWidgetItem(""))
        table.setItem(current_row_count, 10, QTableWidgetItem(""))

        today_str = datetime.now().strftime("%d/%m/%Y")
        table.setItem(current_row_count, 11, QTableWidgetItem(today_str))

        table.setItem(current_row_count, 12, QTableWidgetItem(""))
    
    def remove_deceased_transaction_row(self):
        # 1. تحديد السطر الحالي المختار في الجدول
        current_row = self.detail_deceased_transactions_table.currentRow()
        
        if current_row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد السطر المراد حذفه أولاً.")
            return

        # 2. التحقق مما إذا كانت العملية مسجلة (نفترض أن الـ ID مخفي في العمود 0 مثلاً)
        # ملاحظة: قم بتغيير رقم العمود حسب مكان تخزين المعرف ID في جدولك
        item_id = self.detail_deceased_transactions_table.item(current_row, 0)
        transaction_id = item_id.text() if item_id else ""

        if transaction_id and transaction_id.strip():
            # العملية مسجلة بالفعل في قاعدة البيانات
            reply = QMessageBox.question(
                self, 
                "تأكيد الحذف", 
                "حذف هذه العملية سيؤدي إلى تعديل أرصدة المتوفى والأيتام المرتبطين تلقائياً. هل أنت متأكد؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # هنا تضع كود الحذف من قاعدة البيانات
                if self.delete_transaction_from_db(transaction_id):
                    self.detail_deceased_transactions_table.removeRow(current_row)
                    log_activity(self.db_service.session, self.current_user.id, ActionTypes.DELETE, ResourceTypes.DECEASED_TRANSACTION, resource_id=transaction_id, description=f"تم حذف حركة متوفى من النظام")
                    self.statusBar().showMessage("تم حذف العملية من النظام بنجاح", 8000)
                    self.load_card(self.controller.current_person, PersonType.DECEASED)
        else:
            # العملية جديدة ولم تُسجل بعد (حذف مباشر من الجدول)
            self.detail_deceased_transactions_table.removeRow(current_row)

    def delete_transaction_from_db(self, trans_id):
        """ حذف السجل من قاعدة البيانات وتصحيح أرصدة المتوفى والأيتام """
        db = self.db_service.session
        try:
            # 1. جلب الحركة المراد حذفها
            transaction = db.query(DeceasedTransaction).filter_by(id=trans_id).first()
            if not transaction:
                return False

            # 2. إذا كانت الحركة "سحب" (توزيع للأيتام)، يجب عكس أرصدة الأيتام وحذف حركاتهم
            if transaction.type == TransactionTypeEnum.withdraw:
                # البحث عن حركات الأيتام المرتبطة بهذا التوزيع
                linked_orphan_txns = db.query(Transaction).filter_by(deceased_transaction_id=transaction.id).all()
                
                for o_txn in linked_orphan_txns:
                    # خصم المبلغ من رصيد اليتيم الحالي
                    orphan_bal = db.query(OrphanBalance).filter_by(
                        orphan_id=o_txn.orphan_id, 
                        currency_id=o_txn.currency_id
                    ).first()
                    if orphan_bal:
                        orphan_bal.balance -= o_txn.amount
                    
                    # حذف حركة اليتيم
                    db.delete(o_txn)

                # إعادة المبلغ لرصيد المتوفى (الأمانات)
                deceased_bal = db.query(DeceasedBalance).filter_by(
                    deceased_id=transaction.deceased_id, 
                    currency_id=transaction.currency_id
                ).first()
                if deceased_bal:
                    deceased_bal.balance += transaction.amount

            # 3. إذا كانت الحركة "إيداع" (Deposit)، نخصمها من رصيد المتوفى (الأمانات)
            elif transaction.type == TransactionTypeEnum.deposit:
                deceased_bal = db.query(DeceasedBalance).filter_by(
                    deceased_id=transaction.deceased_id, 
                    currency_id=transaction.currency_id
                ).first()
                if deceased_bal:
                    # تحقق من أن الرصيد يكفي للحذف (اختياري)
                    deceased_bal.balance -= transaction.amount

            # 4. حذف حركة المتوفى الأساسية
            db.delete(transaction)
            
            # تنفيذ التغييرات
            db.commit()
            return True

        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"فشل الحذف وتحديث الأرصدة: {str(e)}")
            return False
    
    def open_add_transaction_dialog(self):
        if not self.controller.current_person:
            return

        selected_currency_id = self.c_combo.currentData()
        selected_currency_code = None
        if selected_currency_id:
            selected_currency = self.db_service.session.query(Currency).get(selected_currency_id)
            selected_currency_code = selected_currency.code if selected_currency and selected_currency.code else None
        if not selected_currency_code:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار العملة من الحقل C_Combo أولاً.")
            return
        
        person_id = self.controller.current_person.id
        dialog = AddTransactionDialog(
            deceased_id=person_id,
            db_service=self.db_service,
            forced_currency_code=selected_currency_code,
            hide_currency_field=True,
            hide_date_field=True,
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted: 
            new_data = dialog.get_transaction_data()
            
            if self.db_service.add_single_deceased_transaction(new_data):
                # بعد الحفظ بنجاح، نقوم بجلب بيانات الشخص مجدداً من الجلسة المفتوحة
                # هذا السطر سيجعل load_card و load_deceased_transaction_tab تعمل بسلام
                self.controller.current_person = self.db_service.session.query(Deceased).get(person_id)
                
                self.load_deceased_transaction_tab() 
                self.load_card(self.controller.current_person, PersonType.DECEASED)
                
                log_activity(self.db_service.session, self.current_user.id, ActionTypes.CREATE, ResourceTypes.DECEASED_TRANSACTION, resource_id=self.controller.current_person.id, description=f"أضيفت حركة جديدة للمتوفى '{self.controller.current_person.name}'")
                QMessageBox.information(self, "نجاح", "تمت إضافة الحركة وتحديث الرصيد بنجاح")

    def add_single_deceased_transaction(self, data):
        db = self.session
        try:
            # 1. إنشاء سجل الحركة الجديد
            new_txn = DeceasedTransaction(**data)
            db.add(new_txn)
            
            # 2. تحديث رصيد المتوفى (DeceasedBalance)
            # البحث عن سجل الرصيد للعملة المحددة
            balance_record = db.query(DeceasedBalance).filter_by(
                deceased_id=data['deceased_id'], 
                currency_id=data['currency_id']
            ).first()
            
            if balance_record:
                if data['type'] == 'deposit':
                    balance_record.balance += data['amount']
                else:
                    balance_record.balance -= data['amount']
            else:
                # إذا لم يكن له سجل رصيد سابق لهذه العملة (حالة نادرة)
                new_balance = DeceasedBalance(
                    deceased_id=data['deceased_id'],
                    currency_id=data['currency_id'],
                    balance=data['amount'] if data['type'] == 'deposit' else -data['amount']
                )
                db.add(new_balance)
                
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"Error adding transaction: {e}")
            return False
    
    # ==== Home Tab ====
    def init_dashboard(self):
        """تهيئة لوحة التحكم (تحديث الملخصات فقط بدون تحميل الجداول)"""
        self.search_input.clear()
        # تحديث الملخصات فقط (أرقام سريعة)
        self.update_summary_lcds()

    def update_summary_lcds(self):
        """تحديث ملخصات الأرقام - محسّن للسرعة"""
        try:
            # استخدام استعلام محسّن بدل استدعاء دوال متعددة
            summary = self.db_service.get_summary_counts()
            
            # تحديث مباشر بدون try/except متكرر لكل LCD
            if summary:
                try:
                    self.lcd_orphans_count.display(summary.get("orphans", 0))
                except: 
                    pass
                try:
                    self.lcd_orphans_older_than_18_count.display(summary.get("orphans_over_18", 0))
                except: 
                    pass
                try:
                    self.lcd_guardians_count.display(summary.get("guardians", 0))
                except: 
                    pass
                try:
                    self.lcd_deceased_people_count.display(summary.get("deceased", 0))
                except: 
                    pass
        except Exception as e:
            logger.warning(f"خطأ في تحديث ملخصات اللوحة: {e}")

    # ===== Load Card =====
    def load_card(self, obj, person_type):
        self.card_name.setText(obj.name)
        self.card_national_id.setText(obj.national_id or "---")

        self.card_phone.hide()
        self.card_phone_icon.hide()
        self.card_phone_label.hide()
        self.container_balance.hide()
        self.card_gender.hide()
        self.card_gender_icon.hide()
        self.card_gender_label.hide()
        self.label_138.hide() # For age in card
        self.label_137.hide() # For age in card
        

        if person_type == PersonType.ORPHAN:
            self.card_badge.setText("يتيم")
            self.card_date.setText(obj.date_birth.strftime("%d/%m/%Y") if obj.date_birth else "---")
            self.card_date_label.setText('تاريخ الميلاد:')
            self.card_gender.setText("ذكر" if obj.gender.value==1 else "أنثى")
            self.card_gender.show()
            self.card_gender_label.show()
            self.card_gender_icon.show()
            self.card_phone.setText(obj.phone or "---")
            self.card_phone.show()
            self.card_phone_label.show()
            self.card_phone_icon.show()
            self.container_balance.show()
            self.label_138.show()
            self.label_137.setText(str(obj.age) if obj.age is not None else "---")
            self.label_137.show()

            balances = {b.currency.code: b.balance for b in obj.balances}
            self.card_shekel_balance.setText(f"{balances.get('ILS',0):,.2f}")
            self.card_dollar_balance.setText(f"{balances.get('USD',0):,.2f}")
            self.card_dinar_balance.setText(f"{balances.get('JOD',0):,.2f}")
            self.card_euro_balance.setText(f"{balances.get('EUR',0):,.2f}")

        elif person_type == PersonType.DECEASED:
            self.card_badge.setText("متوفي")
            self.card_date.setText(obj.date_death.strftime("%d/%m/%Y") if obj.date_death else "---")
            self.card_date_label.setText('تاريخ الوفاة:')
            self.container_balance.show()
            
            balances = {b.currency.code: b.balance for b in obj.balances}
            self.card_shekel_balance.setText(f"{balances.get('ILS',0):,.2f}")
            self.card_dollar_balance.setText(f"{balances.get('USD',0):,.2f}")
            self.card_dinar_balance.setText(f"{balances.get('JOD',0):,.2f}")
            self.card_euro_balance.setText(f"{balances.get('EUR',0):,.2f}")

        elif person_type == PersonType.GUARDIAN:
            self.card_badge.setText("وصي")
            self.card_date.setText(obj.created_at.strftime("%d/%m/%Y"))
            self.card_date_label.setText('تاريخ الإضافة:')
            self.card_phone.setText(obj.phone or "---")
            self.card_phone_label.show()
            self.card_phone.show()
            self.card_phone_icon.show()
            self.container_balance.show()
            
            balances = {b.currency.code: b.balance for b in obj.balances}
            self.card_shekel_balance.setText(f"{balances.get('ILS',0):,.2f}")
            self.card_dollar_balance.setText(f"{balances.get('USD',0):,.2f}")
            self.card_dinar_balance.setText(f"{balances.get('JOD',0):,.2f}")
            self.card_euro_balance.setText(f"{balances.get('EUR',0):,.2f}")

    # ===== Orphan Tabs =====
    def load_orphan_tab(self):
        o = self.controller.current_person
        self.detail_orphan_name.setText(o.name)
        self.detail_orphan_id.setText(o.national_id)
        self.detail_orphan_birth_day.setText(o.date_birth.strftime("%d/%m/%Y") if o.date_birth else "")
        self.detail_orphan_gender.setCurrentIndex(o.gender.value)
        self.detail_orphan_phone.setText(o.phone or "")

        d = o.deceased
        if d:
            self.lineEdit_40.setText(str(d.id))
            self.detail_deceased_name.setText(d.name)
            self.detail_deceased_id.setText(d.national_id)
            self.detail_deceased_date_death.setText(d.date_death.strftime("%d/%m/%Y") if d.date_death else "")
            self.detail_deceased_account_number.setText(d.account_number or "")
            self.detail_deceased_archives_number.setText(d.archives_number or "")
        else:
            self.lineEdit_40.clear()
            self.detail_deceased_name.clear()
            self.detail_deceased_id.clear()
            self.detail_deceased_date_death.clear()
            self.detail_deceased_account_number.clear()
            self.detail_deceased_archives_number.clear()

        # guardian
        primary_link = next((l for l in o.guardian_links if l.is_primary), None)
        if primary_link:
            g = primary_link.guardian
            self.lineEdit_41.setText(str(g.id))
            self.detail_guardian_name.setText(g.name)
            self.detail_guardian_id.setText(g.national_id)
            self.detail_guardian_phone.setText(g.phone or "")
            self.detail_guardian_kinship.setText(primary_link.relation)
            self.detail_guardian_start_date.setText(primary_link.start_date.strftime("%d/%m/%Y") if primary_link.start_date else "")
        else:
            self.lineEdit_41.clear()
            self.detail_guardian_name.clear()
            self.detail_guardian_id.clear()
            self.detail_guardian_phone.clear()
            self.detail_guardian_kinship.clear()
            self.detail_guardian_start_date.clear()

    # ===== Balance Tab =====
    def load_balance_tab(self):
        db = self.db_service
        person = self.controller.current_person
        person_type = self.controller.current_type
        if person_type == PersonType.ORPHAN:
            # balances = {b.currency.code: b.balance for b in person.balances}
            # self.detail_orphan_shekel.setText(f"{balances.get('ILS',0):,.2f}")
            # self.detail_orphan_dollar.setText(f"{balances.get('USD',0):,.2f}")
            # self.detail_orphan_dinar.setText(f"{balances.get('JOD',0):,.2f}")
            # self.detail_orphan_euro.setText(f"{balances.get('EUR',0):,.2f}")
            self.setup_balance_table(self.tableWidget, db.get_orphan_summary(person.id))
        elif person_type == PersonType.DECEASED:
            # balances = {b.currency.code: b.balance for b in person.balances}
            # self.detail_deceased_shekel.setText(f"{balances.get('ILS',0):,.2f}")
            # self.detail_deceased_dollar.setText(f"{balances.get('USD',0):,.2f}")
            # self.detail_deceased_dinar.setText(f"{balances.get('JOD',0):,.2f}")
            # self.detail_deceased_euro.setText(f"{balances.get('EUR',0):,.2f}")
            self.setup_balance_table(self.tableWidget_2, db.get_deceased_summary(person.id))
        elif person_type == PersonType.GUARDIAN:
            self.setup_balance_table(self.tableWidget_3, db.get_guardian_summary(person.id))

    # ===== Transactions Tab =====
    def load_transactions_tab(self):
        o = self.controller.current_person  # الشخص الحالي
        table = self.detail_orphan_transactions_table
        transactions = o.transactions  # قائمة الحركات

        table.setColumnCount(13)
        table.setHorizontalHeaderLabels([
            "ID", "العملة", "نوع الحركة", "المبلغ", "تاريخ الحركة", "ملاحظة",
            "طريقة الدفع", "رقم سند القبض/الصرف", "المودع/المستفيد", "رقم الشيك",
            "تاريخ الاستحقاق", "اسم البنك", "رقم المرجع/الحوالة",
        ])
        table.setColumnHidden(0, True)
        
        # احصل على أسماء العملات من قاعدة البيانات
        db = self.db_service.session
        currency_names = [c.name for c in db.query(Currency).all()]

        table.setRowCount(len(transactions))

        for row_idx, t in enumerate(transactions):
            # ===== ID =====
            table.setItem(row_idx, 0, self._create_readonly_item(str(t.id)))

            # ===== Currency Combo =====
            combo_currency = QComboBox()
            combo_currency.addItems(["اختر"] + currency_names)
            if t.currency:
                idx = combo_currency.findText(t.currency.name)
                combo_currency.setCurrentIndex(idx if idx != -1 else 0)
            table.setCellWidget(row_idx, 1, combo_currency)

            # ===== Transaction Type Combo =====
            combo_type = QComboBox()
            combo_type.addItems(["اختر", "إيداع", "سحب"])
            if t.type == TransactionTypeEnum.deposit:
                combo_type.setCurrentText("إيداع")
            elif t.type == TransactionTypeEnum.withdraw:
                combo_type.setCurrentText("سحب")
            table.setCellWidget(row_idx, 2, combo_type)

            # ===== Amount =====
            table.setItem(row_idx, 3, QTableWidgetItem(f"{t.amount:,.2f}"))

            # ===== Date =====
            table.setItem(
                row_idx, 4,
                QTableWidgetItem(t.created_date.strftime("%d/%m/%Y") if t.created_date else "")
            )
            table.setItem(
                row_idx, 5,
                QTableWidgetItem(t.note or '')
            )
            table.setItem(row_idx, 6, QTableWidgetItem(t.payment_method or ""))
            table.setItem(row_idx, 7, QTableWidgetItem(t.document_number or ""))
            table.setItem(row_idx, 8, QTableWidgetItem(t.person_name or ""))
            table.setItem(row_idx, 9, QTableWidgetItem(t.check_number or ""))
            table.setItem(row_idx, 10, QTableWidgetItem(t.due_date.strftime("%d/%m/%Y") if t.due_date else ""))
            table.setItem(row_idx, 11, QTableWidgetItem(t.bank_name or ""))
            table.setItem(row_idx, 12, QTableWidgetItem(t.reference_number or ""))

    # ===== Deceased Tabs =====
    def load_deceased_tab(self):
        d = self.controller.current_person
        self.detail_deceased_name_2.setText(d.name)
        self.detail_deceased_id_2.setText(d.national_id)
        self.detail_deceased_date_death_2.setText(d.date_death.strftime("%d/%m/%Y") if d.date_death else "")
        self.detail_deceased_account_number_2.setText(d.account_number or "")
        self.detail_deceased_archives_number_2.setText(d.archives_number or "")

        if d.orphans:
            first_orphan = d.orphans[0]
            if first_orphan.guardian_links:
                link = next((l for l in first_orphan.guardian_links if l.is_primary), first_orphan.guardian_links[0])
                g = link.guardian
                self.detail_guardian_name_2.setText(g.name)
                self.detail_guardian_id_2.setText(g.national_id)
                self.detail_guardian_phone_2.setText(g.phone or "")
                self.detail_guardian_kinship_2.setText(link.relation or "")
                self.detail_guardian_start_date_2.setText(link.start_date.strftime("%d/%m/%Y") if link.start_date else "")

    def load_deceased_transaction_tab(self):
        table = self.detail_deceased_transactions_table
        id = self.controller.current_person.id
        db = self.db_service.session
        transactions = db.query(DeceasedTransaction).filter_by(deceased_id=id).all()
        # currency_names = [c.name for c in db.query(Currency).all()]

        table.setRowCount(len(transactions))

        for row_idx, t in enumerate(transactions):
            # ===== ID =====
            table.setItem(row_idx, 0, self._create_readonly_item(str(t.id)))

            combo_currency = QComboBox()
            combo_currency.addItems(["اختر"] + [c.name for c in db.query(Currency).all()])
            if t.currency:
                idx = combo_currency.findText(t.currency.name)
                combo_currency.setCurrentIndex(idx if idx != -1 else 0)
            table.setCellWidget(row_idx, 1, combo_currency)

            combo_type = QComboBox()
            combo_type.addItems(["اختر", "إيداع", "سحب"])
            combo_type.setCurrentText("إيداع" if t.type == TransactionTypeEnum.deposit else "سحب")
            table.setCellWidget(row_idx, 2, combo_type)

            combo_payment_method = QComboBox()
            combo_payment_method.addItems(["اختر", "نقداً", "شيك", "تحويل بنكي"])
            if t.payment_method:
                pm_idx = combo_payment_method.findText(t.payment_method)
                combo_payment_method.setCurrentIndex(pm_idx if pm_idx != -1 else 0)
            table.setCellWidget(row_idx, 4, combo_payment_method)

            # ===== Amount =====
            table.setItem(row_idx, 3, QTableWidgetItem(f"{t.amount:,.2f}" or '---'))
            table.setItem(row_idx, 5, QTableWidgetItem(t.receipt_number or ""))
            table.setItem(row_idx, 6, QTableWidgetItem(t.payer_name or ""))
            table.setItem(row_idx, 7, QTableWidgetItem(t.bank_name or ""))
            table.setItem(row_idx, 8, QTableWidgetItem(t.check_number or ""))
            table.setItem(row_idx, 9, QTableWidgetItem(t.due_date.strftime("%d/%m/%Y") if t.due_date else ""))
            table.setItem(row_idx, 10, QTableWidgetItem(t.reference_number or ""))
            table.setItem(row_idx, 11, QTableWidgetItem(t.created_date.strftime("%d/%m/%Y") if t.created_date else "---"))
            table.setItem(row_idx, 12, QTableWidgetItem(t.note or ''))

    def load_deceased_orphans_tab(self):
        """تحميل جدول الأيتام المرتبط بالمتوفي مع أرصدة العملات"""
        d = self.controller.current_person
        if not d:
            return

        orphans = d.orphans
        table = self.detail_deceased_orphans_table
        table.setRowCount(len(orphans))
        # table.setToolTip("يمكن الإضافة أو الحذف فقط من هذه القائمة؛ لتعديل بيانات اليتيم افتح صفحة تفاصيل اليتيم.")

        for row_idx, o in enumerate(orphans):
            # ID (read-only)
            id_item = QTableWidgetItem(str(o.id))
            id_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 0, id_item)

            # Name / NID / DOB: make read-only for existing orphans
            name_item = QTableWidgetItem(o.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 1, name_item)

            nid_item = QTableWidgetItem(o.national_id)
            nid_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 2, nid_item)

            primary_link = next(
                (link for link in o.guardian_links if link.is_primary),
                None
            )
            guardian = primary_link.guardian if primary_link else None
            
            guardian_name_item = QTableWidgetItem(guardian.name if guardian else "")
            guardian_name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 3, guardian_name_item)
            
            guardian_id = QTableWidgetItem(guardian.national_id if guardian else "")
            guardian_id.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 4, guardian_id)
            
            relation_item = QTableWidgetItem(primary_link.relation if primary_link and primary_link.relation else "")
            relation_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 5, relation_item)

            dob_item = QTableWidgetItem(o.date_birth.strftime("%d/%m/%Y") if o.date_birth else "")
            dob_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_idx, 6, dob_item)

            gender_combo = QComboBox()
            gender_combo.addItems(["اختر", "ذكر", "أنثى"])
            gender_combo.setCurrentIndex(o.gender.value) # نفترض أن 1=ذكر، 2=أنثى
            gender_combo.setEnabled(False)  # disable editing gender
            table.setCellWidget(row_idx, 7, gender_combo)

            # أرصدة العملات (قراءة فقط)
            balances_map = {bal.currency.code: bal.balance for bal in o.balances}
            ils_item = QTableWidgetItem(f"{balances_map.get('ILS', 0):,.2f}")
            usd_item = QTableWidgetItem(f"{balances_map.get('USD', 0):,.2f}")
            jod_item = QTableWidgetItem(f"{balances_map.get('JOD', 0):,.2f}")
            eur_item = QTableWidgetItem(f"{balances_map.get('EUR', 0):,.2f}")

            readonly_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            ils_item.setFlags(readonly_flags)
            usd_item.setFlags(readonly_flags)
            jod_item.setFlags(readonly_flags)
            eur_item.setFlags(readonly_flags)

            table.setItem(row_idx, 8, ils_item)
            table.setItem(row_idx, 9, usd_item)
            table.setItem(row_idx, 10, jod_item)
            table.setItem(row_idx, 11, eur_item)

    # ===== Guardian Tabs =====
    def load_guardian_tab(self):
        g = self.controller.current_person
        self.detail_guardian_name_3.setText(g.name)
        self.detail_guardian_id_3.setText(g.national_id)
        self.detail_guardian_phone_3.setText(g.phone or "")

    def load_guardian_transactions_tab(self):
        g = self.controller.current_person
        table = self.transactions_table_3
        db = self.db_service.session

        table.setColumnCount(13)
        table.setHorizontalHeaderLabels([
            "ID", "تاريخ الحركة", "نوع الحركة", "العملة", "المبلغ", "ملاحظة",
            "طريقة الدفع", "رقم سند القبض/الصرف", "المودع/المستفيد", "رقم الشيك",
            "تاريخ الاستحقاق", "اسم البنك", "رقم المرجع/الحوالة",
        ])
        table.setColumnHidden(0, True)

        currency_names = [c.name for c in db.query(Currency).all()]

        transactions = (
            db.query(GuardianTransaction)
            .filter(GuardianTransaction.guardian_id == g.id)
            .order_by(GuardianTransaction.created_date.desc(), GuardianTransaction.id.desc())
            .all()
        )

        table.setRowCount(len(transactions))

        for row_idx, t in enumerate(transactions):
            table.setItem(row_idx, 0, self._create_readonly_item(str(t.id)))
            table.setItem(row_idx, 1, QTableWidgetItem(t.created_date.strftime("%d/%m/%Y") if t.created_date else ""))

            type_combo = QComboBox()
            type_combo.addItems(["اختر", "إيداع", "سحب"])
            type_combo.setCurrentText("إيداع" if t.type == TransactionTypeEnum.deposit else "سحب")
            table.setCellWidget(row_idx, 2, type_combo)

            currency_combo = QComboBox()
            currency_combo.addItems(["اختر"] + currency_names)
            if t.currency:
                idx = currency_combo.findText(t.currency.name)
                currency_combo.setCurrentIndex(idx if idx != -1 else 0)
            table.setCellWidget(row_idx, 3, currency_combo)

            table.setItem(row_idx, 4, QTableWidgetItem(f"{t.amount:,.2f}"))
            table.setItem(row_idx, 5, QTableWidgetItem(t.note or ""))
            table.setItem(row_idx, 6, QTableWidgetItem(t.payment_method or ""))
            table.setItem(row_idx, 7, QTableWidgetItem(t.document_number or ""))
            table.setItem(row_idx, 8, QTableWidgetItem(t.person_name or ""))
            table.setItem(row_idx, 9, QTableWidgetItem(t.check_number or ""))
            table.setItem(row_idx, 10, QTableWidgetItem(t.due_date.strftime("%d/%m/%Y") if t.due_date else ""))
            table.setItem(row_idx, 11, QTableWidgetItem(t.bank_name or ""))
            table.setItem(row_idx, 12, QTableWidgetItem(t.reference_number or ""))

    def load_guardian_orphans_tab(self):
        """تحميل جدول الأيتام مع كافة التفاصيل: الأرصدة، التواريخ، وصلة القرابة، وحالة الوصاية"""
        g = self.controller.current_person
        links = g.orphan_links 
        table = self.detail_guardian_orphans_table
        table.setRowCount(len(links))
        
        # ترتيب الأعمدة المحدث:
        # 0:ID, 1:الاسم, 2:الهوية, 3:الميلاد, 4:الجنس, 5:الوصي الأساسي (Checkbox)
        # 6:القرابة, 7:البدء, 8:الانتهاء, 9-12:الأرصدة

        for row_idx, link in enumerate(links):
            o = link.orphan

            # --- 1. البيانات الشخصية (أعمدة 0-4) ---
            table.setItem(row_idx, 0, self._create_readonly_item(str(o.id)))
            table.setItem(row_idx, 1, self._create_readonly_item(o.name))
            table.setItem(row_idx, 2, self._create_readonly_item(o.national_id))
            
            dob_str = o.date_birth.strftime("%d/%m/%Y") if o.date_birth else ""
            table.setItem(row_idx, 3, self._create_readonly_item(dob_str))

            gender_combo = QComboBox()
            gender_combo.addItems(["اختر", "ذكر", "أنثى"])
            idx = o.gender.value if hasattr(o.gender, 'value') else int(o.gender)
            gender_combo.setCurrentIndex(idx)
            gender_combo.setEnabled(False)
            table.setCellWidget(row_idx, 4, gender_combo)

            # --- 2. عمود الوصي الأساسي (Checkbox) ---
            # نقوم بإنشاء Widget يحتوي على Checkbox في المنتصف
            check_widget = QWidget()
            check_layout = QHBoxLayout(check_widget)
            is_primary_check = QCheckBox()
            
            # ضبط الحالة بناءً على قاعدة البيانات
            is_primary_check.setChecked(link.is_primary if hasattr(link, 'is_primary') else False)
            
            # تعطيله للقراءة فقط
            # is_primary_check.setEnabled(False)
            
            check_layout.addWidget(is_primary_check)
            check_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            check_layout.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row_idx, 5, check_widget)
            
            # --- 3. صلة القرابة ---
            kinship_str = link.relation if link.relation else ""
            table.setItem(row_idx, 6, QTableWidgetItem(kinship_str))
            
            # --- 4. تواريخ الوصاية ---
            start_date_str = link.start_date.strftime("%d/%m/%Y") if link.start_date else ""
            table.setItem(row_idx, 7, self._create_readonly_item(start_date_str))

            end_date_str = link.end_date.strftime("%d/%m/%Y") if hasattr(link, 'end_date') and link.end_date else "مستمر"
            end_item = self._create_readonly_item(end_date_str)
            
            # تلوين الحالة (أحمر للمنتهي، أخضر للمستمر)
            is_ended = hasattr(link, 'end_date') and link.end_date
            color = Qt.GlobalColor.red if is_ended else Qt.GlobalColor.darkGreen
            end_item.setForeground(color)
            table.setItem(row_idx, 8, end_item)

            # --- 5. أرصدة العملات (أعمدة 9-12) ---
            balances_map = {bal.currency.code: bal.balance for bal in o.balances}
            for col, code in enumerate(("ILS", "USD", "JOD", "EUR"), start=9):
                val = f"{balances_map.get(code, 0):,.2f}"
                b_item = self._create_readonly_item(val)
                
                # إذا كان الرصيد صفراً، اجعله باهتاً (كما طلبنا سابقاً)
                if balances_map.get(code, 0) == 0:
                    b_item.setForeground(Qt.GlobalColor.gray)
                
                table.setItem(row_idx, col, b_item)

    # ==== Add Person Methods ===
    # Add new deceased file
    def clear_add_deceased_form(self):
        # Clear deceased fields
        try:
            self.add_deceased_name.clear()
            self.add_deceased_id.clear()
            self.add_deceased_account_number.clear()
            self.add_deceased_archives_number.clear()
            self.add_deceased_date_death.clear()

            # Clear guardian fields
            self.add_guardian_name.clear()
            self.add_guardian_id.clear()
            self.add_guardian_phone.clear()
            self.add_guardian_kinship.clear()
            self.add_guardian_start_date.clear()
            
            # اسم البنك (ILS)
            self.lineEdit_14.clear()
            # اسم البنك (USD)
            self.lineEdit_19.clear()
            # اسم البنك (JOD)
            self.lineEdit_26.clear()
            # اسم البنك (EUR)
            self.lineEdit_33.clear()
            # =====================
            # رصيد الشيكل (شيك)
            self.lineEdit_12.clear()
            self.lineEdit_13.clear()
            # رصيد الدولار (شيك)
            self.lineEdit_17.clear()
            self.lineEdit_18.clear()
            # رصيد الدينار (شيك)
            self.lineEdit_24.clear()
            self.lineEdit_25.clear()
            # رصيد اليورو (شيك)
            self.lineEdit_31.clear()
            self.lineEdit_32.clear()
            # =====================
            # رقم الحوالة (شيكل)
            self.lineEdit_15.clear()
            # رقم الحوالة (دولار)
            self.lineEdit_20.clear()
            # رقم الحوالة (دينار)
            self.lineEdit_27.clear()
            # رقم الحوالة (يورو)
            self.lineEdit_34.clear()
            
            self.lineEdit_9.clear()
            self.lineEdit_22.clear()
            self.lineEdit_29.clear()
            self.lineEdit_36.clear()
            
            self.comboBox.setCurrentIndex(0)
            self.comboBox_2.setCurrentIndex(0)
            self.comboBox_3.setCurrentIndex(0)
            self.comboBox_4.setCurrentIndex(0)
            
            # self.buttonGroup.button(0).setChecked(True)

            # Clear orphans table entirely
            table = self.add_deceased_orphans_table
            table.setRowCount(0)
            
            self.lineEdit_37.clear()
        except Exception as e:
            QMessageBox.warning(self, "تحذير", f"حدث خطأ أثناء تفريغ الحقول: {e}")
    
    def get_deceased_form_data(self):
        deceased_name = self.add_deceased_name.text().strip()
        deceased_national_id = self.add_deceased_id.text().strip()
        deceased_account_number = self.add_deceased_account_number.text().strip() or None
        deceased_archives_number = self.add_deceased_archives_number.text().strip() or None
        deceased_date_death = try_get_date(self.add_deceased_date_death.text().strip())
        
        g_id = self.lineEdit_37.text().strip() or None
        guardian_name = self.add_guardian_name.text().strip()
        guardian_national_id = self.add_guardian_id.text().strip()
        guardian_phone = self.add_guardian_phone.text().strip() or None
        guardian_kinship = self.add_guardian_kinship.text().strip()
        guardian_start_date = try_get_date(self.add_guardian_start_date.text().strip())

        db = self.db_service.session
        
        # التحقق من بيانات المتوفى
        if not deceased_name:
            raise ValueError("يرجى إدخال اسم المتوفّى")
        if db.query(Deceased).filter_by(name=deceased_name).first():
            raise ValueError(f"اسم المتوفي '{deceased_name}' موجود بالفعل في النظام.")
        
        if deceased_national_id and (not deceased_national_id.isdigit() or len(deceased_national_id) != 9):
            raise ValueError("رقم الهوية للمتوفّى غير صالح (يجب أن يكون 9 أرقام)")
        if deceased_national_id and db.query(Deceased).filter_by(national_id=deceased_national_id).first():
            raise ValueError(f"رقم هوية المتوفي {deceased_national_id} موجود بالفعل.")
        
        deceased_date_death = parse_and_validate_date(deceased_date_death)
        guardian_start_date = parse_and_validate_date(guardian_start_date)

        # التحقق من بيانات الوصي
        if not guardian_name:
            raise ValueError("يرجى إدخال اسم الوصي الشرعي")
        if not g_id and db.query(Guardian).filter_by(name=guardian_name).first():
            raise ValueError(f"اسم الوصي '{guardian_name}' موجود بالفعل في النظام.")
        
        if guardian_national_id and (not guardian_national_id.isdigit() or len(guardian_national_id) != 9):
            raise ValueError("رقم الهوية للوصي غير صالح (يجب أن يكون 9 أرقام)")
        if not g_id and guardian_national_id and db.query(Guardian).filter_by(national_id=guardian_national_id).first():
            raise ValueError(f"رقم هوية الوصي '{guardian_national_id}' موجود بالفعل في النظام.")
        

        if not guardian_kinship:
            raise ValueError("يرجى إدخال صلة القرابة بين اليتيم والوصي")

        deceased_data = {
            "name": deceased_name,
            "national_id": deceased_national_id,
            "date_death": deceased_date_death,
            "account_number": deceased_account_number,
            "archives_number": deceased_archives_number,
        }
        
        guardian_data = {
            "id": g_id,
            "name": guardian_name,
            "national_id": guardian_national_id,
            "phone": guardian_phone,
            "relation": guardian_kinship,
            "start_date": guardian_start_date,
        }
        
        return deceased_data, guardian_data

    def add_new_deceased(self):
        table = self.add_deceased_orphans_table
        db = self.db_service.session  # الوصول لجلسة قاعدة البيانات
        
        # objects = db.query(Deceased).all()
        # if len(objects) > 5: 
        #     QMessageBox.critical(self, 'خطأ', 'لقد تجاوزت الحد المسموح به')
        #     return
        
        try:
            # 1. جلب البيانات الأساسية من النماذج والجدول
            deceased_data, guardian_data = self.get_deceased_form_data()
            
            existing_guardian = None
            if guardian_data['id']:
                existing_guardian = db.query(Guardian).get(guardian_data['id'])
            else:
                # check by name or nid
                filters = []
                if guardian_data.get('name'):
                    filters.append(Guardian.name == guardian_data['name'])
                if guardian_data.get('national_id'):
                    filters.append(Guardian.national_id == guardian_data['national_id'])
                if filters:
                    existing_guardian = db.query(Guardian).filter(
                        or_(*filters)
                    ).first()
                if existing_guardian:
                    raise ValueError(f"هذا الوصي مسجل مسبقاً في النظام:\n\nالاسم: {existing_guardian.name}\nرقم الهوية: {existing_guardian.national_id or '---'}\nرقم الجوال: {existing_guardian.phone or '---'}")
            
            # if not guardian_data['id'] and existing_guardian:
            #     # # مقارنة البيانات (الاسم، الهاتف، إلخ)
            #     # has_changes = (
            #     #     existing_guardian.name != guardian_data.get('name') or 
            #     #     existing_guardian.phone != guardian_data.get('phone')
            #     # )
            #     # if has_changes:
            #         QMessageBox.warning(self, "تحذير", f"هذا الوصي مسجل مسبقاً في النظام:\n\nالاسم: {existing_guardian.name}\nرقم الهوية: {existing_guardian.national_id or '---'}\nرقم الجوال: {existing_guardian.phone or '---'}")
            #         return
            
            orphans_data = self.get_orphans_table_data(table)
            
            if not orphans_data:
                raise ValueError("يجب إضافة يتيم واحد على الأقل للمتوفى.")

            # 2. فحص الأيتام وجلب أرصدتهم الحقيقية من قاعدة البيانات (الأرصدة الأصلية)
            existing_orphans_names = []
            for o_data in orphans_data:
                # البحث عن اليتيم برقم الهوية
                orphan = None
                if not o_data.get('id'):
                    filters = []
                    if o_data.get('name'):
                        filters.append(Orphan.name == o_data['name'])
                    if o_data.get('national_id'):
                        filters.append(Orphan.national_id == o_data['national_id'])
                    if filters:
                        orphan = db.query(Orphan).filter(or_(*filters)).first()
                    if orphan:
                        raise ValueError(f"هذا اليتيم مسجل مسبقاً في النظام:\n\nالاسم: {orphan.name}\nرقم الهوية: {orphan.national_id or '---'}\nتاريخ الميلاد: {orphan.date_birth.strftime('%d/%m/%Y') if orphan.date_birth else '---'}\nالجنس: {'ذكر' if orphan.gender == GenderEnum.male else 'أنثى'}\nرقم الجوال: {orphan.phone or '---'}")
                else:
                    orphan = db.query(Orphan).get(int(o_data['id']))
                
                exists = orphan
                if exists and exists.deceased_id:
                    raise ValueError(f'اليتيم "{exists.name}" صاحب هوية رقم "{exists.national_id}" مسجل ومرتبط بملف متوفي آخر')
                # تهيئة مفاتيح الأرصدة الأصلية في القاموس لمنع أخطاء الـ Key Error
                
                for code in ["ils", "usd", "jod", "eur"]:
                    o_data[f'original_{code}_balance'] = Decimal('0')

                if exists:
                    existing_orphans_names.append(f'{exists.name} | رقم الهوية: {exists.national_id}')
                    # تخزين الأرصدة الحقيقية الحالية لليتيم الموجود مسبقاً
                    for bal in exists.balances:
                        currency_code = bal.currency.code.lower()
                        o_data[f'original_{currency_code}_balance'] = Decimal(str(bal.balance))
                
                # ملاحظة: إذا كان اليتيم جديداً، ستبقى الأرصدة الأصلية 0 كما هي معرفة فوق.

            # 3. طلب تأكيد في حال وجود أيتام مسجلين مسبقاً (نقل ملفات)
            if existing_orphans_names:
                names_str = "\n".join(existing_orphans_names)
                reply = QMessageBox.question(
                    self, "تأكيد نقل أيتام",
                    f"الأيتام التالية أسماؤهم مسجلون مسبقاً في النظام:\n\n{names_str}\n\n"
                    "هل أنت متأكد من نقلهم لهذا المتوفى الجديد وتحديث أرصدتهم؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            # -------------------------------------------------------

            all_currencies_details = {
                "ILS": {
                    "amount": Decimal(self.lineEdit_9.text().strip() or 0),
                    "payment_method": self.comboBox.currentText(),
                    "receipt_number": self.lineEdit_10.text().strip(),
                    "payer_name": self.lineEdit_11.text().strip(),
                    "check_number": self.lineEdit_12.text().strip(),
                    "due_date": try_get_date(self.lineEdit_13.text().strip()),
                    "bank_name": self.lineEdit_14.text().strip(),
                    "reference_number": self.lineEdit_15.text().strip(),
                },
                "USD": {
                    "amount": Decimal(self.lineEdit_22.text().strip() or 0),
                    "payment_method": self.comboBox_2.currentText(),
                    "receipt_number": self.lineEdit_16.text().strip(),
                    "payer_name": self.lineEdit_21.text().strip(),
                    "check_number": self.lineEdit_17.text().strip(),
                    "due_date": try_get_date(self.lineEdit_18.text().strip()),
                    "bank_name": self.lineEdit_19.text().strip(),
                    "reference_number": self.lineEdit_20.text().strip(),
                },
                "JOD": {
                    "amount": Decimal(self.lineEdit_29.text().strip() or 0),
                    "payment_method": self.comboBox_3.currentText(),
                    "receipt_number": self.lineEdit_23.text().strip(),
                    "payer_name": self.lineEdit_28.text().strip(),
                    "check_number": self.lineEdit_24.text().strip(),
                    "due_date": try_get_date(self.lineEdit_25.text().strip()),
                    "bank_name": self.lineEdit_26.text().strip(),
                    "reference_number": self.lineEdit_27.text().strip(),
                },
                "EUR": {
                    "amount": Decimal(self.lineEdit_36.text().strip() or 0),
                    "payment_method": self.comboBox_4.currentText(),
                    "receipt_number": self.lineEdit_30.text().strip(),
                    "payer_name": self.lineEdit_35.text().strip(),
                    "check_number": self.lineEdit_31.text().strip(),
                    "due_date": try_get_date(self.lineEdit_32.text().strip()),
                    "bank_name": self.lineEdit_33.text().strip(),
                    "reference_number": self.lineEdit_34.text().strip(),
                },
            }
            
            total_limits = {
                "ILS": Decimal(self.lineEdit_9.text().strip() or "0"),
                "USD": Decimal(self.lineEdit_22.text().strip() or "0"),
                "JOD": Decimal(self.lineEdit_29.text().strip() or "0"),
                "EUR": Decimal(self.lineEdit_36.text().strip() or "0")
            }
            
            # 2. إجراء الحسبة الرياضية للتوزيع
            selected_mode = self.buttonGroup.checkedButton().text()
            count = len(orphans_data)
            for code in ["ILS", "USD", "JOD", "EUR"]:
                field = f"{code.lower()}_balance"
                orig_field = f"original_{field}"
                amount_to_distribute = total_limits[code]

                if amount_to_distribute <= 0 and selected_mode != 'يدوي':
                    continue

                if selected_mode in ['بالتساوي', 'ذكر مثل حظ الانثيين']:
                    # 1. تحديد إجمالي الأسهم بناءً على الوضع المختار
                    if selected_mode == 'بالتساوي':
                        total_shares = count
                    else:
                        total_shares = sum(2 if o['gender'] == GenderEnum.male else 1 for o in orphans_data)

                    if total_shares > 0:
                        # 2. حساب الحصة الأساسية لكل يتيم (مع حفظ الأجزاء العشرية)
                        shares_list = []
                        remainders_with_idx = []  # قائمة الأجزاء العشرية مع فهارس الأيتام
                        total_exact = Decimal('0')
                        
                        for idx, o in enumerate(orphans_data):
                            # تحديد المضروب (2 للذكر في الميراث، و 1 للجميع في التساوي)
                            multiplier = 1
                            if selected_mode == 'ذكر مثل حظ الانثيين':
                                multiplier = 2 if o['gender'] == GenderEnum.male else 1
                            
                            # حساب الحصة الدقيقة (بدون تقريب)
                            exact_share = (amount_to_distribute * multiplier / total_shares)
                            
                            # اقتطع الجزء الصحيح فقط
                            base_share = int(exact_share * 100) / 100  # الجزء الصحيح
                            base_share = Decimal(str(base_share)).quantize(Decimal('0.01'))
                            shares_list.append(base_share)
                            total_exact += base_share
                            
                            # احفظ الجزء العشري للاستفادة منه لاحقاً
                            remainder_decimal = exact_share - base_share
                            remainders_with_idx.append((remainder_decimal, idx))
                        
                        # 3. توزيع البواقي على الأيتام ذوي أكبر أجزاء عشرية (طريقة البواقي الأكبر)
                        remainder = amount_to_distribute - total_exact
                        if remainder > 0:
                            # ترتيب الأيتام حسب حجم أجزاءهم العشرية (من الأكبر للأصغر)
                            remainders_with_idx.sort(reverse=True, key=lambda x: x[0])
                            
                            # توزيع 0.01 على الأيتام الذين لديهم أكبر أجزاء عشرية
                            for remainder_val, idx in remainders_with_idx:
                                if remainder <= 0:
                                    break
                                add_amount = min(Decimal('0.01'), remainder)
                                shares_list[idx] += add_amount
                                remainder -= add_amount
                        
                        # 4. تطبيق الأرصدة النهائية
                        for idx, o in enumerate(orphans_data):
                            o[field] = o[orig_field] + shares_list[idx]

                elif selected_mode == 'يدوي':
                    # فحص هل مجموع ما أدخل في الجدول يتجاوز (القديم + المتاح حالياً)
                    sum_in_table = sum(Decimal(str(o.get(field, 0))) for o in orphans_data)
                    sum_original = sum(o[orig_field] for o in orphans_data)
                    
                    added_by_user = sum_in_table - sum_original
                    
                    if added_by_user > amount_to_distribute:
                        raise ValueError(f"إجمالي المبالغ المضافة لعملة {code} يتجاوز المبلغ المتاح في رصيد المتوفي.")
            
            
            # 3. تنفيذ العملية كاملة في قاعدة البيانات
            result = self.db_service.add_deceased_and_orphans(
                deceased_data, 
                guardian_data, 
                orphans_data,
                all_currencies_details,
                selected_mode
            )
            
            if result:
                log_activity(
                    session=self.db_service.session,
                    user_id=self.current_user.id,
                    action=ActionTypes.CREATE,
                    resource_type=ResourceTypes.DECEASED,
                    resource_id=result['deceased_id'],
                    description=f"تم إضافة ملف متوفى جديد: {deceased_data['name']} مع {len(orphans_data)} يتيم/يتيمة."
                )
                self.statusBar().showMessage("تم اضافة البيانات بنجاح", 8000)
                self.clear_add_deceased_form()
        except ValueError as ve:
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            print(e)
            QMessageBox.critical(self, "خطأ في النظام", f"حدث خطأ غير متوقع: {str(e)}")
    
    # Add new orphan file
    def clear_add_orphan_form(self):
        try:
            # Orphan fields
            self.add_orphan_name.clear()
            self.add_orphan_gender.setCurrentIndex(0)
            self.add_orphan_id.clear()
            self.add_orphan_birth_day.clear()
            self.add_orphan_phone.clear()
            self.add_orphan_shekel.clear()
            self.add_orphan_dollar.clear()
            self.add_orphan_dinar.clear()
            self.add_orphan_euro.clear()

            # Deceased fields (second panel)
            self.add_deceased_name_2.clear()
            self.add_deceased_id_2.clear()
            self.add_deceased_account_number_2.clear()
            self.add_deceased_archives_number_2.clear()
            self.add_deceased_date_death_2.clear()

            # Guardian fields (second panel)
            self.add_guardian_name_2.clear()
            self.add_guardian_id_2.clear()
            self.add_guardian_phone_2.clear()
            self.add_guardian_kinship_2.clear()
            self.add_guardian_start_date_2.clear()
            
            self.lineEdit_38.clear()
            self.lineEdit_39.clear()
        except Exception as e:
            QMessageBox.warning(self, "تحذير", f"حدث خطأ أثناء تفريغ الحقول: {e}")

    def add_new_orphan(self):
        db = self.db_service.session
        
        # objects = db.query(Orphan).all()
        # if len(objects) > 5: 
        #     QMessageBox.critical(self, 'خطأ', 'لقد تجاوزت الحد المسموح به')
        #     return
        
        try:
            # --- 1. جلب البيانات من الواجهة ---
            orphan_name = self.add_orphan_name.text().strip()
            orphan_gender = self.add_orphan_gender.currentIndex()
            orphan_national_id = self.add_orphan_id.text().strip()
            orphan_birth_day = try_get_date(self.add_orphan_birth_day.text().strip())
            orphan_phone = self.add_orphan_phone.text().strip() or None

            deceased_name = self.add_deceased_name_2.text().strip()
            deceased_national_id = self.add_deceased_id_2.text().strip()
            deceased_account_number = self.add_deceased_account_number_2.text().strip() or None
            deceased_archives_number = self.add_deceased_archives_number_2.text().strip() or None
            deceased_date_death = try_get_date(self.add_deceased_date_death_2.text().strip())

            guardian_name = self.add_guardian_name_2.text().strip()
            guardian_national_id = self.add_guardian_id_2.text().strip()
            guardian_phone = self.add_guardian_phone_2.text().strip() or None
            guardian_kinship = self.add_guardian_kinship_2.text().strip()
            guardian_start_date = try_get_date(self.add_guardian_start_date_2.text().strip())

            ils = parse_decimal(self.add_orphan_shekel.text(), 'شيكل')
            usd = parse_decimal(self.add_orphan_dollar.text(), 'دولار')
            jod = parse_decimal(self.add_orphan_dinar.text(), 'دينار')
            eur = parse_decimal(self.add_orphan_euro.text(), 'يورو')
            note = self.trans_note_input.text().strip() or None
            
            d_id = self.lineEdit_38.text().strip()
            g_id = self.lineEdit_39.text().strip()

            # --- 2. التحقق من بيانات اليتيم ---
            if not orphan_name:
                raise ValueError("اسم اليتيم مطلوب")
            if db.query(Orphan).filter_by(name=orphan_name).first():
                raise ValueError(f"اسم اليتيم '{orphan_name}' مسجل بالفعل في  النظام")
            
            if orphan_national_id and (not orphan_national_id.isdigit() or len(orphan_national_id) != 9):
                raise ValueError("رقم هوية اليتيم يجب أن يتكون من 9 أرقام")
            if orphan_national_id and db.query(Orphan).filter_by(national_id=orphan_national_id).first():
                raise ValueError(f"رقم هوية اليتيم '{orphan_national_id}' مسجل بالفعل في النظام")
            
            if orphan_gender == 0:
                raise ValueError("يرجى اختيار جنس اليتيم")
            # if not orphan_birth_day:
            #     raise ValueError("تاريخ ميلاد اليتيم مطلوب")
            dob_qdate = parse_and_validate_date(orphan_birth_day)

            # منع التكرار لليتيم
            # if db.query(Orphan).filter_by(national_id=orphan_national_id).first():
            #     raise ValueError(f"اليتيم صاحب الهوية {orphan_national_id} موجود مسبقاً")

            # --- 3. التحقق من بيانات المتوفى ---
            if not deceased_name:
                raise ValueError("اسم المتوفى مطلوب")
            if not d_id and db.query(Deceased).filter_by(name=deceased_name).first():
                raise ValueError(f"اسم المتوفي '{deceased_name}' مسجل بالفعل في النظام")
            
            if deceased_national_id and (not deceased_national_id.isdigit() or len(deceased_national_id) != 9):
                raise ValueError("رقم هوية المتوفى يجب أن يتكون من 9 أرقام")
            if not d_id and deceased_national_id and db.query(Deceased).filter_by(national_id=deceased_national_id).first():
                raise ValueError(f"رقم هوية المتوفي '{deceased_national_id}' مسجل بالفعل في النظام")
            
            # --- 4. التحقق من بيانات الوصي ---
            if not guardian_name:
                raise ValueError("اسم الوصي مطلوب")
            if not g_id and db.query(Guardian).filter_by(name=guardian_name).first():
                raise ValueError(f"اسم الوصي '{guardian_name}' مسجل بالفعل في  النظام")
            
            if guardian_national_id and (not guardian_national_id.isdigit() or len(guardian_national_id) != 9):
                raise ValueError("رقم هوية الوصي يجب أن يتكون من 9 أرقام")
            if not g_id and guardian_national_id and db.query(Guardian).filter_by(national_id=guardian_national_id).first():
                raise ValueError(f"رقم هوية الوصي '{guardian_national_id}' مسجل بالفعل في النظام")
            
            if not guardian_kinship:
                raise ValueError("يرجى تحديد صلة قرابة الوصي")

            # --- 5. معالجة المتوفى (إنشاء أو تحديث اختياري) ---
            
            # deceased = db.query(Deceased).filter_by(national_id=deceased_national_id).first()
            if not d_id:
                d_death_q = parse_and_validate_date(deceased_date_death)
                deceased = Deceased(
                    name=deceased_name,
                    national_id=deceased_national_id,
                    date_death=d_death_q,
                    account_number=deceased_account_number or None,
                    archives_number=deceased_archives_number or None,
                )
                db.add(deceased)
                db.flush()
            else:
                deceased = db.query(Deceased).get(int(d_id))
            #     # تحديث الحقول الاختيارية فقط إذا كانت فارغة
            #     if not deceased.account_number and deceased_account_number:
            #         deceased.account_number = deceased_account_number
            #     if not deceased.archives_number and deceased_archives_number:
            #         deceased.archives_number = deceased_archives_number
            #     if not deceased.date_death and deceased_date_death:
            #         d_death_q = validate_date(deceased_date_death, False)
            #         deceased.date_death = qdate_to_date(d_death_q)

            # --- 6. معالجة الوصي (إنشاء أو تحديث اختياري) ---
            
            # guardian = db.query(Guardian).filter_by(national_id=guardian_national_id).first()
            if not g_id:
                guardian = Guardian(
                    name=guardian_name,
                    national_id=guardian_national_id,
                    phone=guardian_phone or None,
                )
                db.add(guardian)
                db.flush()
            else:
                guardian = db.query(Guardian).get(int(g_id))
            #     if not guardian.phone and guardian_phone:
            #         guardian.phone = guardian_phone

            # --- 7. إنشاء اليتيم وربطه بالأرصدة والوصي ---
            orphan = Orphan(
                deceased_id=deceased.id,
                name=orphan_name,
                national_id=orphan_national_id,
                date_birth=dob_qdate,
                gender=GenderEnum(orphan_gender),
                phone=orphan_phone or None,
            )
            db.add(orphan)
            db.flush()

            # الأرصدة
            self.db_service._create_opening_balances(
                db=db, orphan_id=orphan.id, 
                balances={'ILS': ils, 'USD': usd, 'JOD': jod, 'EUR': eur}, 
                create_transactions=True,
                note=note,
            )

            # ربط الوصي
            g_start_q = parse_and_validate_date(guardian_start_date)
            db.add(OrphanGuardian(
                orphan_id=orphan.id,
                guardian_id=guardian.id,
                is_primary=True,
                relation=guardian_kinship,
                start_date=g_start_q,
            ))

            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.CREATE, ResourceTypes.ORPHAN, resource_id=orphan.id, description=f"تم إضافة يتيم جديد: {orphan.name} تحت ملف المتوفى: {deceased.name} والوصي: {guardian.name}.")
            self.statusBar().showMessage("تمت إضافة البيانات بنجاح", 8000)
            self.clear_add_orphan_form()

        except Exception as e:
            db.rollback()
            QMessageBox.warning(self, "خطأ في التحقق", str(e))

    # Add new guardian file
    def clear_add_guardian_form(self):
        try:
            # Guardian fields
            self.add_guardian_name_3.clear()
            self.add_guardian_id_3.clear()
            self.add_guardian_phone_3.clear()
            self.add_guardian_kinship_3.clear()
            self.add_guardian_start_date_3.clear()

            # Clear orphans table entirely
            table = self.add_guardian_orphans_table
            table.setRowCount(0)
        except Exception as e:
            QMessageBox.warning(self, "تحذير", f"حدث خطأ أثناء تفريغ الحقول: {e}")

    def add_new_guardian(self):
        guardian_name = self.add_guardian_name_3.text().strip()
        guardian_national_id = self.add_guardian_id_3.text().strip()
        guardian_phone = self.add_guardian_phone_3.text().strip()
        guardian_kinship = self.add_guardian_kinship_3.text().strip()
        guardian_start_date = try_get_date(self.add_guardian_start_date_3.text().strip())
        
        table = self.add_guardian_orphans_table
        db = self.db_service.session
        
        # objects = db.query(Guardian).all()
        # if len(objects) > 5: 
        #     QMessageBox.critical(self, 'خطأ', 'لقد تجاوزت الحد المسموح به')
        #     return
        
        try:
            # ===== 1. التحقق من البيانات الأساسية =====
            if not guardian_name:
                raise ValueError("يرجى إدخال اسم الوصي الشرعي")
            if db.query(Guardian).filter_by(name=guardian_name).first():
                raise ValueError(f"اسم الوصي '{guardian_name}' موجود بالفعل في النظام.")
            
            if guardian_national_id and (not guardian_national_id.isdigit() or len(guardian_national_id) != 9):
                raise ValueError("رقم هوية الوصي غير صالح (يجب أن يكون 9 أرقام)")
            if guardian_national_id and db.query(Guardian).filter_by(national_id=guardian_national_id).first():
                raise ValueError(f"رقم هوية الوصي {guardian_national_id} موجود بالفعل في النظام.")
            
            if not guardian_kinship:
                raise ValueError("يرجى إدخال العلاقة بين اليتيم والوصي")

            # التحقق من التاريخ وتحويله بشكل آمن لقاعدة البيانات
            g_start_q = parse_and_validate_date(guardian_start_date)
            g_start_date_py = g_start_q #if g_start_q else datetime.now().date()

            # جلب بيانات الأيتام من الجدول قبل البدء
            orphans_data = self.get_orphans_table_data(table)
            if not orphans_data:
                raise ValueError("يرجى إضافة يتيم واحد على الأقل للجدول.")
            
            existing_orphans = []
            for odata in orphans_data:
                orphan_obj = None
                if not odata.get('id'):
                    filters = []
                    if odata['name']:
                        filters.append(Orphan.name == odata['name'])
                    if odata['national_id']:
                        filters.append(Orphan.national_id == odata['national_id'])
                    if filters:
                        orphan_obj = db.query(Orphan).filter(or_(*filters)).first()

                    if orphan_obj:
                        raise ValueError(f"هذا اليتيم مسجل مسبقاً في النظام:\n\nالاسم: {orphan_obj.name}\nرقم الهوية: {orphan_obj.national_id or '---'}\nتاريخ الميلاد: {orphan_obj.date_birth.strftime('%d/%m/%Y') if orphan_obj.date_birth else '---'}\nالجنس: {'ذكر' if orphan_obj.gender == GenderEnum.male else 'أنثى'}\nرقم الجوال: {orphan_obj.phone or '---'}\n\nإذا كنت تحاول نقل وصاية يتيم موجود مسبقاً، يرجى اختيار اليتيم من النظام بدلاً من إدخال بياناته يدوياً.")
                    
                else:
                    # ===== 2. فحص الأيتام المسجلين مسبقاً لطلب تأكيد نقل الوصاية =====
                    orphan_obj = db.query(Orphan).get(odata['id'])
                    current_primary = db.query(OrphanGuardian).filter_by(orphan_id=orphan_obj.id, is_primary=True).first()
                    if current_primary:
                        existing_orphans.append(f"- {orphan_obj.name} (وصيه الحالي: {current_primary.guardian.name})")

            if existing_orphans:
                orphans_list_str = "\n".join(existing_orphans)
                reply = QMessageBox.question(
                    self, "تأكيد نقل وصاية",
                    f"الأيتام التاليين لديهم أوصياء مسجلون بالفعل:\n\n{orphans_list_str}\n\n"
                    "هل أنت متأكد من إنهاء وصايتهم الحالية وجعل هذا الوصي هو الأساسي؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            # ===== 3. معالجة بيانات الوصي =====
            guardian = Guardian(
                name=guardian_name,
                national_id=guardian_national_id,
                phone=guardian_phone or None,
            )
            db.add(guardian)
            db.flush()

            # ===== 4. ربط الأيتام وتطبيق منطق النقل الفعلي =====
            for odata in orphans_data:
                # البحث عن اليتيم أو إنشاؤه حسب وجوده في النظام
                orphan_obj = None
                if odata.get('id'):
                    orphan_obj = db.query(Orphan).get(odata['id'])
                
                if not orphan_obj:
                    # إنشاء يتيم جديد كلياً
                    orphan_obj = Orphan(
                        deceased_id=None,
                        name=odata['name'],
                        national_id=odata['national_id'],
                        date_birth=odata['date_birth'],
                        gender=odata['gender'],
                    )
                    db.add(orphan_obj)
                    db.flush()
                    
                    # إضافة أرصدة افتتاحية لليتيم الجديد
                    balances = {
                        'ILS': odata.get('ils_balance', 0),
                        'USD': odata.get('usd_balance', 0),
                        'JOD': odata.get('jod_balance', 0),
                        'EUR': odata.get('eur_balance', 0),
                    }
                    self.db_service._create_opening_balances(db, orphan_obj.id, balances, True)
                else:
                    # اليتيم موجود: إنهاء أي وصاية أساسية قديمة
                    db.query(OrphanGuardian).filter_by(orphan_id=orphan_obj.id, is_primary=True).update({
                        "is_primary": False,
                        "end_date": datetime.now().date()
                    })

                # إنشاء رابط الوصاية الجديد كوصاية أساسية
                link = OrphanGuardian(
                    orphan_id=orphan_obj.id,
                    guardian_id=guardian.id,
                    is_primary=True, # أصبح الآن هو الوصي الأساسي
                    relation=guardian_kinship,
                    start_date=g_start_date_py,
                )
                db.add(link)

            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.CREATE, ResourceTypes.GUARDIAN, resource_id=guardian.id, description=f"تم إضافة وصي شرعي جديد: {guardian.name} مع {len(orphans_data)} يتيم/يتيمة.")
            self.statusBar().showMessage("تم تسجيل البيانات بنجاح", 8000)
            self.clear_add_guardian_form()

        except Exception as e:
            db.rollback()
            QMessageBox.warning(self, "خطأ", str(e))
    
    # ==== Delete selcted person record ====
    def delete_person_record(self, obj):
        db = self.db_service.session
        try:
            if type(obj).__name__.lower() == 'deceased' and  obj.orphans:
                QMessageBox.warning(self, "خطأ", "لا يمكن حذف هذا المتوفى لأنه مرتبط بأيتام. يرجى حذف الأيتام المرتبطين أولاً.")
                return
            
            confirm = QMessageBox.question(
                self, "تأكيد الحذف",
                f"هل أنت متأكد من حذف السجل الخاص بـ {obj.name}؟ لا يمكن التراجع عن هذا الإجراء.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                db.delete(obj)
                db.commit()
                log_activity(self.db_service.session, self.current_user.id, ActionTypes.DELETE, type(obj).__name__.lower(), resource_id=obj.id, description=f"تم حذف سجل {type(obj).__name__} الخاص بـ {obj.name}.")
                QMessageBox.information(self, "نجاح", "تم حذف السجل بنجاح.")
                self.tabWidget.setCurrentIndex(0)  # العودة إلى تبويب الرئيسية
        except Exception as e:
            db.rollback()
            QMessageBox.warning(self, "خطأ", str(e))
    
    def _save_orphan_record(self, db, orphan):
        try:
            d_id = self.lineEdit_40.text().strip()
            g_id = self.lineEdit_41.text().strip()
            # --- 1. تحديث بيانات اليتيم الشخصية ---
            orphan_name = self.detail_orphan_name.text().strip()
            orphan_national_id = self.detail_orphan_id.text().strip() or None
            if not orphan_name:
                raise ValueError("اسم اليتيم مطلوب")
            if orphan_national_id and (not orphan_national_id.isdigit() or len(orphan_national_id) != 9):
                raise ValueError("رقم هوية اليتيم يجب أن يتكون من 9 أرقام")
            
            orphan_obj = None
            filters = []
            filters.append(Orphan.name == orphan_name)
            if orphan_national_id:
                filters.append(Orphan.national_id == orphan_national_id)
            if filters:
                orphan_obj = db.query(Orphan).filter(Orphan.id != orphan.id, or_(*filters)).first()
            
            if orphan_obj:
                raise ValueError('الإسم أو رقم الهوية مسجل مسبقاً في النظام')

            orphan_gender = self.detail_orphan_gender.currentIndex()
            if orphan_gender == 0:
                raise ValueError("يرجى اختيار جنس اليتيم.")
            
            dob_text = try_get_date(self.detail_orphan_birth_day.text().strip())
            dob_text = parse_and_validate_date(dob_text)
            # if not dob_text:
            #     raise ValueError("يرجى إدخال تاريخ ميلاد اليتيم.")
            
            orphan.name = orphan_name
            orphan.national_id = orphan_national_id
            orphan.gender = GenderEnum(orphan_gender)
            orphan.date_birth = dob_text
            orphan.phone = self.detail_orphan_phone.text().strip() or None
            
            if d_id:
                orphan.deceased_id = int(d_id)

            # --- 2. منطق نقل الوصاية مع معالجة التكرار (حل مشكلة 1062 Duplicate Entry) ---
            new_guardian_id = self.detail_guardian_id.text().strip()
            new_guardian_name = self.detail_guardian_name.text().strip()
            new_kinship = self.detail_guardian_kinship.text().strip()
            
            # if not new_guardian_name:
            #     raise ValueError("يرجى إدخال اسم الوصي.")
            # guardian_obj = None
            # if not new_guardian_id and new_guardian_name:
            #     guardian_obj = db.query(Guardian).filter_by(name=new_guardian_name).first()
            #     if guardian_obj:
            #         raise ValueError(f"اسم الوصي '{new_guardian_name}' مسجل بالفعل في النظام")
            
            
            if g_id and not new_kinship:
                raise ValueError("يرجى إدخال صلة القرابة بين اليتيم والوصي.")
            
            start_date_text = try_get_date(self.detail_guardian_start_date.text().strip())
            today = datetime.now().date()
            g_start_date = parse_and_validate_date(start_date_text)

            # البحث عن الرابط الأساسي الحالي
            current_link = next((l for l in orphan.guardian_links if l.is_primary), None)
            print(current_link)
            # حالة تغيير الوصي
            if g_id and current_link and current_link.guardian.id != int(g_id):
                old_name = current_link.guardian.name
                print(f"الوصي الحالي: {old_name}، الوصي الجديد: {new_guardian_name}")
                reply = QMessageBox.question(
                    self, 'تأكيد نقل الوصاية',
                    f"هل أنت متأكد من إنهاء وصاية {old_name} ونقلها إلى {new_guardian_name}؟",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
                )

                if reply == QMessageBox.StandardButton.Yes:
                    # أ. إنهاء الوصاية القديمة
                    current_link.is_primary = False
                    current_link.end_date = today
                    
                    # ب. البحث عن الوصي الجديد أو إنشاؤه
                    new_guardian = db.query(Guardian).get(int(g_id))
                    # if not new_guardian:
                    #     new_guardian = Guardian(
                    #         name=new_guardian_name,
                    #         national_id=new_guardian_id,
                    #         phone=self.detail_guardian_phone.text().strip()
                    #     )
                    #     db.add(new_guardian)
                    #     db.flush() # للحصول على id الوصي الجديد

                    # ج. فحص وجود رابط سابق بين اليتيم والوصي الجديد (حل المشكلة الأساسية)
                    existing_link = db.query(OrphanGuardian).filter_by(
                        orphan_id=orphan.id, 
                        guardian_id=new_guardian.id
                    ).first()

                    if existing_link:
                        # إعادة تفعيل الرابط القديم بدلاً من إضافة واحد جديد مكرر
                        existing_link.is_primary = True
                        existing_link.relation = new_kinship
                        existing_link.start_date = g_start_date
                        existing_link.end_date = None
                    else:
                        # إنشاء رابط جديد إذا لم يسبق لهما الارتباط
                        new_link = OrphanGuardian(
                            orphan_id=orphan.id,
                            guardian_id=new_guardian.id,
                            relation=new_kinship,
                            is_primary=True,
                            start_date=g_start_date
                        )
                        db.add(new_link)
                else:
                    return # إلغاء الحفظ إذا رفض المستخدم النقل

            elif g_id and current_link and current_link.guardian.id == int(g_id):
                # تحديث بيانات الوصي الحالي إذا لم يتغير الشخص
                current_link.relation = new_kinship
                # إذا رغبت بتحديث تاريخ البدء للوصي الحالي يمكن تفعيل السطر التالي:
                current_link.start_date = g_start_date
            elif g_id and not current_link:
                
                existing_link = db.query(OrphanGuardian).filter_by(
                    orphan_id=orphan.id, 
                    guardian_id=int(g_id),
                ).first()
                
                if existing_link:
                    existing_link.is_primary = True
                    existing_link.relation = new_kinship
                    existing_link.start_date = g_start_date
                    existing_link.end_date = None
                else:
                    # إنشاء رابط جديد إذا لم يسبق لهما الارتباط
                    new_link = OrphanGuardian(
                        orphan_id=orphan.id,
                        guardian_id=int(g_id),
                        relation=new_kinship,
                        is_primary=True,
                        start_date=g_start_date
                    )
                    db.add(new_link)

            # --- 3. معالجة الحركات المالية والأرصدة ---
            transactions = self.get_orphan_transactions_table(self.detail_orphan_transactions_table)
            
            def get_or_create_balance(c_id):
                b_rec = db.query(OrphanBalance).filter_by(orphan_id=orphan.id, currency_id=c_id).first()
                if not b_rec:
                    b_rec = OrphanBalance(orphan_id=orphan.id, currency_id=c_id, balance=Decimal('0.00'))
                    db.add(b_rec)
                    db.flush()
                return b_rec

            for index, trans in enumerate(transactions):
                row_num = index + 1
                new_amount = Decimal(str(trans['amount']))
                new_type_enum = TransactionTypeEnum.deposit if trans['type'] == "إيداع" else TransactionTypeEnum.withdraw
                new_curr_obj = db.query(Currency).filter_by(name=trans['currency']).first()
                
                if not new_curr_obj:
                    raise ValueError(f"السطر {row_num}: العملة المختارة غير معرفة.")

                if trans['id']: # تعديل حركة سابقة
                    trans_obj = db.query(Transaction).get(trans['id'])
                    if (trans_obj.currency_id != new_curr_obj.id or trans_obj.type != new_type_enum or trans_obj.amount != new_amount):
                        
                        old_bal_rec = get_or_create_balance(trans_obj.currency_id)
                        new_bal_rec = get_or_create_balance(new_curr_obj.id)
                        
                        # عكس الحركة القديمة
                        temp_old_bal = old_bal_rec.balance - trans_obj.amount if trans_obj.type == TransactionTypeEnum.deposit else old_bal_rec.balance + trans_obj.amount
                        
                        # حساب الرصيد الجديد المتوقع
                        check_bal = temp_old_bal if trans_obj.currency_id == new_curr_obj.id else new_bal_rec.balance
                        final_bal = check_bal + new_amount if new_type_enum == TransactionTypeEnum.deposit else check_bal - new_amount

                        if final_bal < 0:
                            raise ValueError(f"السطر {row_num}: الرصيد سيصبح سالباً ({final_bal:,.2f}).")

                        # تطبيق التغييرات
                        old_bal_rec.balance = temp_old_bal
                        if trans_obj.currency_id == new_curr_obj.id:
                            old_bal_rec.balance = final_bal
                        else:
                            new_bal_rec.balance += new_amount if new_type_enum == TransactionTypeEnum.deposit else -new_amount
                        
                        trans_obj.currency_id = new_curr_obj.id
                        trans_obj.type = new_type_enum
                        trans_obj.amount = new_amount

                    trans_obj.note = trans['note']
                    trans_obj.created_date = datetime.strptime(trans['date'], "%d/%m/%Y").date()
                    trans_obj.payment_method = trans.get("payment_method")
                    trans_obj.document_number = trans.get("document_number")
                    trans_obj.person_name = trans.get("person_name")
                    trans_obj.check_number = trans.get("check_number")
                    trans_obj.due_date = trans.get("due_date")
                    trans_obj.bank_name = trans.get("bank_name")
                    trans_obj.reference_number = trans.get("reference_number")

                else: # إضافة حركة جديدة
                    bal_rec = get_or_create_balance(new_curr_obj.id)
                    if new_type_enum == TransactionTypeEnum.withdraw and bal_rec.balance < new_amount:
                        raise ValueError(f"السطر {row_num}: الرصيد الحالي ({bal_rec.balance:,.2f}) لا يكفي.")
                    
                    bal_rec.balance += new_amount if new_type_enum == TransactionTypeEnum.deposit else -new_amount
                    db.add(Transaction(orphan_id=orphan.id, currency_id=new_curr_obj.id, type=new_type_enum, 
                                    amount=new_amount, note=trans['note'], 
                                    created_date=datetime.strptime(trans['date'], "%d/%m/%Y").date(),
                                    payment_method=trans.get("payment_method"),
                                    document_number=trans.get("document_number"),
                                    person_name=trans.get("person_name"),
                                    check_number=trans.get("check_number"),
                                    due_date=trans.get("due_date"),
                                    bank_name=trans.get("bank_name"),
                                    reference_number=trans.get("reference_number"),
                                    ))

            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.UPDATE, ResourceTypes.ORPHAN, resource_id=orphan.id, description=f"تم تعديل سجل اليتيم: {orphan.name}.")
            self.statusBar().showMessage("تم تحديث البيانات بنجاح", 8000)
            self.open_person(orphan, PersonType.ORPHAN)

        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ نظام", f"حدث خطأ: {str(e)}")

    def _save_guardian_record(self, db, guardian):
        current_index = self.person_record_tabs.currentIndex()
        try:
            # 1. تحديث بيانات الوصي الأساسية (التبويب 7)
            if current_index == 7:
                guardian_name = self.detail_guardian_name_3.text().strip()
                new_nid = self.detail_guardian_id_3.text().strip()
                new_phone = self.detail_guardian_phone_3.text().strip() or None
                
                if not guardian_name:
                    raise ValueError("اسم الوصي مطلوب.")
                if new_nid and (not new_nid.isdigit() or len(new_nid) != 9):
                    raise ValueError("رقم هوية الوصي يجب أن يتكون من 9 أرقام")
                
                guardian_obj = None
                filters = []
                filters.append(Guardian.name == guardian_name)
                if new_nid:
                    filters.append(Guardian.national_id == new_nid)
                if filters:
                    guardian_obj = db.query(Guardian).filter(Guardian.id != guardian.id, or_(*filters)).first()
                
                if guardian_obj:
                    raise ValueError('الإسم أو رقم الهوية مسجل مسبقاً في النظام')
                
                guardian.name = guardian_name
                guardian.national_id = new_nid
                guardian.phone = new_phone

            # 2. تعديل حركات الوصي من الجدول (التبويب 9)
            elif current_index == 9:
                transactions = self.get_guardian_transactions_table(self.transactions_table_3)

                existing_transactions = db.query(GuardianTransaction).filter_by(guardian_id=guardian.id).all()
                existing_map = {t.id: t for t in existing_transactions}
                submitted_ids = {t["id"] for t in transactions if t.get("id")}

                def get_or_create_guardian_balance(currency_id):
                    rec = db.query(GuardianBalance).filter_by(
                        guardian_id=guardian.id,
                        currency_id=currency_id,
                    ).first()
                    if not rec:
                        rec = GuardianBalance(guardian_id=guardian.id, currency_id=currency_id, balance=Decimal("0"))
                        db.add(rec)
                        db.flush()
                    return rec

                # حذف الحركات التي تم حذفها من الجدول
                for old_id, old_txn in existing_map.items():
                    if old_id in submitted_ids:
                        continue

                    old_bal = get_or_create_guardian_balance(old_txn.currency_id)
                    if old_txn.type == TransactionTypeEnum.deposit:
                        if old_bal.balance < old_txn.amount:
                            raise ValueError("لا يمكن حذف حركة إيداع لأن الرصيد الحالي أقل من مبلغها")
                        old_bal.balance -= old_txn.amount
                    else:
                        old_bal.balance += old_txn.amount
                    db.delete(old_txn)

                # إضافة/تعديل الحركات الموجودة في الجدول
                for row_num, trans in enumerate(transactions, start=1):
                    currency_obj = db.query(Currency).filter_by(name=trans["currency"]).first()
                    if not currency_obj:
                        raise ValueError(f"السطر {row_num}: العملة غير موجودة")

                    trans_type = TransactionTypeEnum.deposit if trans["type"] == "إيداع" else TransactionTypeEnum.withdraw

                    tx_date = parse_and_validate_date(trans["date"])
                    tx_datetime = datetime.combine(tx_date, datetime.min.time()) if tx_date else datetime.now()

                    if trans.get("id"):
                        old_txn = existing_map.get(trans["id"])
                        if not old_txn or old_txn.guardian_id != guardian.id:
                            raise ValueError(f"السطر {row_num}: تعذر العثور على الحركة لتعديلها")

                        old_bal = get_or_create_guardian_balance(old_txn.currency_id)
                        if old_txn.type == TransactionTypeEnum.deposit:
                            if old_bal.balance < old_txn.amount:
                                raise ValueError(f"السطر {row_num}: لا يمكن عكس حركة الإيداع القديمة لأن الرصيد الحالي أقل من مبلغها")
                            old_bal.balance -= old_txn.amount
                        else:
                            old_bal.balance += old_txn.amount

                        new_bal = get_or_create_guardian_balance(currency_obj.id)
                        if trans_type == TransactionTypeEnum.withdraw and new_bal.balance < trans["amount"]:
                            raise ValueError(f"السطر {row_num}: الرصيد الحالي لا يكفي لتنفيذ السحب")

                        new_bal.balance += trans["amount"] if trans_type == TransactionTypeEnum.deposit else -trans["amount"]

                        old_txn.currency_id = currency_obj.id
                        old_txn.type = trans_type
                        old_txn.amount = trans["amount"]
                        old_txn.note = trans.get("note") or None
                        old_txn.created_date = tx_datetime
                        old_txn.payment_method = trans.get("payment_method")
                        old_txn.document_number = trans.get("document_number")
                        old_txn.person_name = trans.get("person_name")
                        old_txn.check_number = trans.get("check_number")
                        old_txn.due_date = trans.get("due_date")
                        old_txn.bank_name = trans.get("bank_name")
                        old_txn.reference_number = trans.get("reference_number")
                    else:
                        bal = get_or_create_guardian_balance(currency_obj.id)
                        if trans_type == TransactionTypeEnum.withdraw and bal.balance < trans["amount"]:
                            raise ValueError(f"السطر {row_num}: الرصيد الحالي لا يكفي لتنفيذ السحب")

                        bal.balance += trans["amount"] if trans_type == TransactionTypeEnum.deposit else -trans["amount"]

                        db.add(GuardianTransaction(
                            guardian_id=guardian.id,
                            deceased_id=None,
                            currency_id=currency_obj.id,
                            type=trans_type,
                            amount=trans["amount"],
                            note=trans.get("note") or None,
                            created_date=tx_datetime,
                            created_at=datetime.now(),
                            payment_method=trans.get("payment_method"),
                            document_number=trans.get("document_number"),
                            person_name=trans.get("person_name"),
                            check_number=trans.get("check_number"),
                            due_date=trans.get("due_date"),
                            bank_name=trans.get("bank_name"),
                            reference_number=trans.get("reference_number"),
                        ))

            # 3. معالجة قائمة الأيتام (التبويب 10)
            elif current_index == 10:
                orphans_list_data = self.get_orphans_table_data(self.detail_guardian_orphans_table, require_at_least_one=False)
                today = datetime.now().date()
                print(orphans_list_data)
                # return
                
                for data in orphans_list_data:
                    orphan_obj = None
                    if data.get("id"):
                        orphan_obj = db.query(Orphan).get(data["id"])
                    
                    if not orphan_obj:
                        orphan_obj = db.query(Orphan).filter_by(national_id=data["national_id"]).first()

                    if not orphan_obj:
                        # إنشاء يتيم جديد كلياً
                        orphan_obj = Orphan(
                            name=data["name"],
                            national_id=data["national_id"],
                            date_birth=data["date_birth"],
                            gender=data["gender"]
                        )
                        db.add(orphan_obj)
                        db.flush()

                    # --- منطق التنبيه ونقل الوصاية ---
                    is_p = data.get("is_primary", False)
                    
                    if is_p:
                        # البحث عن وصي أساسي آخر نشط حالياً
                        other_active_link = db.query(OrphanGuardian).filter(
                            OrphanGuardian.orphan_id == orphan_obj.id,
                            OrphanGuardian.guardian_id != guardian.id,
                            OrphanGuardian.is_primary == True,
                            OrphanGuardian.end_date == None
                        ).first()

                        should_transfer = True
                        if other_active_link:
                            # إظهار التنبيه للمستخدم
                            old_guardian_name = other_active_link.guardian.name
                            reply = QMessageBox.question(
                                self, "تأكيد نقل وصاية",
                                f"اليتيم ({orphan_obj.name}) يتبع حالياً للوصي ({old_guardian_name}) كوصي أساسي.\n\n"
                                f"هل تريد إنهاء وصاية ({old_guardian_name}) ونقل الوصاية الأساسية إلى ({guardian.name})؟",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No
                            )
                            
                            if reply == QMessageBox.StandardButton.No:
                                should_transfer = False
                                is_p = False # لا تجعله أساسياً لهذا الوصي إذا رفض المستخدم النقل

                        if should_transfer:
                            # إنهاء وصاية الأوصياء الآخرين
                            db.query(OrphanGuardian).filter(
                                OrphanGuardian.orphan_id == orphan_obj.id,
                                OrphanGuardian.guardian_id != guardian.id,
                                OrphanGuardian.end_date == None 
                            ).update({
                                OrphanGuardian.is_primary: False, 
                                OrphanGuardian.end_date: today
                            }, synchronize_session=False)
                    

                    # إدارة ربط الوصي الحالي باليتيم (تحديث أو إضافة)
                    link = db.query(OrphanGuardian).filter_by(
                        guardian_id=guardian.id,
                        orphan_id=orphan_obj.id
                    ).first()

                    if not link:
                        new_link = OrphanGuardian(
                            orphan_id=orphan_obj.id,
                            guardian_id=guardian.id,
                            is_primary=is_p,
                            relation=data["relation"],
                            start_date=data.get("start_date") or today,
                            end_date=None
                        )
                        db.add(new_link)
                    else:
                        link.is_primary = is_p
                        link.relation = data["relation"]
                        if is_p:
                            link.end_date = None
                        else:
                            link.end_date = today
                        
                        if data.get("start_date"):
                            link.start_date = data["start_date"]

            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.UPDATE, ResourceTypes.GUARDIAN, resource_id=guardian.id, description=f"تم تعديل سجل الوصي الشرعي: {guardian.name}.")
            self.statusBar().showMessage("تم تحديث البيانات بنجاح", 8000)
            self.open_person(guardian, PersonType.GUARDIAN)

        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            print(e)
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"حدث خطأ غير متوقع: {str(e)}")

    def _save_deceased_record(self, db, deceased):
        try:
            current_index = self.person_record_tabs.currentIndex()

            # --- 1. استخراج والتحقق من بيانات المتوفى (القسم الأيمن في الصورة) ---
            deceased_name = self.detail_deceased_name_2.text().strip()
            deceased_nid = self.detail_deceased_id_2.text().strip()
            
            if not deceased_name:
                raise ValueError("اسم المتوفي مطلوب")
            if deceased_nid and (not deceased_nid.isdigit() or len(deceased_nid) != 9):
                raise ValueError("رقم هوية المتوفي يجب أن يتكون من 9 أرقام")
            
            deceased_object = None
            filters = []
            filters.append(Deceased.name == deceased_name)
            if deceased_nid:
                filters.append(Deceased.national_id == deceased_nid)
            if filters:
                deceased_object = db.query(Deceased).filter(Deceased.id != deceased.id, or_(*filters)).first()
            
            if deceased_object:
                raise ValueError('الإسم أو رقم الهوية مسجل مسبقاً في النظام')

            if current_index == 5:
                transactions = self.get_deceased_transactions_table(self.detail_deceased_transactions_table)
                existing_transactions = db.query(DeceasedTransaction).filter_by(deceased_id=deceased.id).all()
                existing_map = {t.id: t for t in existing_transactions}

                def get_or_create_deceased_balance(currency_id):
                    rec = db.query(DeceasedBalance).filter_by(
                        deceased_id=deceased.id,
                        currency_id=currency_id,
                    ).first()
                    if not rec:
                        rec = DeceasedBalance(deceased_id=deceased.id, currency_id=currency_id, balance=Decimal("0"))
                        db.add(rec)
                        db.flush()
                    return rec

                def apply_deceased_balance_delta(currency_id, delta: Decimal):
                    bal_rec = get_or_create_deceased_balance(currency_id)
                    new_balance = Decimal(str(bal_rec.balance or 0)) + Decimal(str(delta or 0))
                    if new_balance < 0:
                        raise ValueError("الرصيد الحالي للمتوفي لا يكفي لتنفيذ السحب")
                    bal_rec.balance = new_balance

                for row_num, trans in enumerate(transactions, start=1):
                    currency_obj = db.query(Currency).filter_by(name=trans["currency"]).first()
                    if not currency_obj:
                        raise ValueError(f"السطر {row_num}: العملة غير موجودة")

                    trans_type = TransactionTypeEnum.deposit if trans["type"] == "إيداع" else TransactionTypeEnum.withdraw
                    tx_date = trans.get("created_date")
                    tx_datetime = datetime.combine(tx_date, datetime.min.time()) if tx_date else datetime.now()

                    if trans.get("id"):
                        old_txn = existing_map.get(trans["id"])
                        if not old_txn or old_txn.deceased_id != deceased.id:
                            raise ValueError(f"السطر {row_num}: تعذر العثور على الحركة لتعديلها")

                        linked_orphan_count = db.query(Transaction).filter_by(deceased_transaction_id=old_txn.id).count()
                        linked_guardian_count = db.query(GuardianTransaction).filter_by(deceased_transaction_id=old_txn.id).count()
                        has_linked_distribution = (linked_orphan_count + linked_guardian_count) > 0

                        old_amount = Decimal(str(old_txn.amount or 0))
                        old_type = old_txn.type
                        changed_main_financial_fields = (
                            old_txn.currency_id != currency_obj.id
                            or old_type != trans_type
                            or old_amount != Decimal(str(trans["amount"]))
                        )

                        if has_linked_distribution and changed_main_financial_fields:
                            raise ValueError(
                                f"السطر {row_num}: لا يمكن تعديل (العملة/النوع/المبلغ) لحركة مرتبطة بتوزيع."
                            )

                        if changed_main_financial_fields and not has_linked_distribution:
                            reverse_delta = -old_amount if old_type == TransactionTypeEnum.deposit else old_amount
                            apply_deceased_balance_delta(old_txn.currency_id, reverse_delta)

                            new_delta = trans["amount"] if trans_type == TransactionTypeEnum.deposit else -trans["amount"]
                            apply_deceased_balance_delta(currency_obj.id, new_delta)

                        old_txn.currency_id = currency_obj.id
                        old_txn.type = trans_type
                        old_txn.amount = trans["amount"]
                        old_txn.payment_method = trans.get("payment_method")
                        old_txn.receipt_number = trans.get("receipt_number")
                        old_txn.payer_name = trans.get("payer_name")
                        old_txn.bank_name = trans.get("bank_name")
                        old_txn.check_number = trans.get("check_number")
                        old_txn.due_date = trans.get("due_date")
                        old_txn.reference_number = trans.get("reference_number")
                        old_txn.created_date = tx_datetime
                        old_txn.note = trans.get("note")
                    else:
                        new_delta = trans["amount"] if trans_type == TransactionTypeEnum.deposit else -trans["amount"]
                        apply_deceased_balance_delta(currency_obj.id, new_delta)

                        db.add(DeceasedTransaction(
                            deceased_id=deceased.id,
                            currency_id=currency_obj.id,
                            amount=trans["amount"],
                            type=trans_type,
                            payment_method=trans.get("payment_method"),
                            receipt_number=trans.get("receipt_number"),
                            payer_name=trans.get("payer_name"),
                            bank_name=trans.get("bank_name"),
                            check_number=trans.get("check_number"),
                            due_date=trans.get("due_date"),
                            reference_number=trans.get("reference_number"),
                            created_date=tx_datetime,
                            note=trans.get("note"),
                        ))

                db.commit()
                log_activity(
                    self.db_service.session,
                    self.current_user.id,
                    ActionTypes.UPDATE,
                    ResourceTypes.DECEASED_TRANSACTION,
                    resource_id=deceased.id,
                    description=f"تم تعديل حركات المتوفى: {deceased.name}."
                )
                self.statusBar().showMessage("تم تحديث حركات المتوفى بنجاح", 8000)
                self.open_person(deceased, PersonType.DECEASED)
                return

            # --- 2. استخراج والتحقق من بيانات الوصي (القسم الأيسر في الصورة) ---
            # guardian_id = self.detail_guardian_id_2.text().strip()
            # guardian_name = self.detail_guardian_name_2.text().strip()
            # guardian_kinship = self.detail_guardian_kinship_2.text().strip() # صلة القرابة
            
            # if not guardian_id or not guardian_name or not guardian_kinship:
            #     raise ValueError("بيانات الوصي الأساسي (الاسم، الهوية، صلة القرابة) إلزامية.")

            # --- 3. جلب بيانات الأيتام من الجدول (الظاهر في صورة 1.PNG) ---
            table = self.detail_deceased_orphans_table
            orphans_data = self.get_orphans_table_data(table, require_at_least_one=False)
            print(orphans_data)
            # return
            
            # # --- 4. التحقق من تضارب الوصاية الأساسية ---
            # orphans_with_conflicts = []
            # for odata in orphans_data:
            #     if odata.get('id'):
            #         # البحث عن أي وصي أساسي حالي مختلف
            #         current_link = db.query(OrphanGuardian).filter(
            #             OrphanGuardian.orphan_id == odata['id'],
            #             OrphanGuardian.is_primary == True
            #         ).first()
                    
            #         if current_link and current_link.guardian.national_id != guardian_id:
            #             orphans_with_conflicts.append(
            #                 f"• {odata['name']} (وصيه الحالي: {current_link.guardian.name})"
            #             )

            # # عرض تحذير للمستخدم في حال وجود تضارب
            # if orphans_with_conflicts:
            #     msg = "تنبيه: الأيتام التاليين مرتبطين بأوصياء أساسيين آخرين:\n\n"
            #     msg += "\n".join(orphans_with_conflicts)
            #     msg += "\n\nعند الحفظ، سيتم إلغاء الوصاية القديمة وتعيين هذا الوصي كوصي أساسي وحيد. هل تريد الاستمرار؟"
                
            #     reply = QMessageBox.question(self, "تأكيد نقل الوصاية", msg,
            #                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            #     if reply == QMessageBox.StandardButton.No:
            #         return

            # --- 5. تنفيذ عمليات الحفظ في قاعدة البيانات ---
            today = datetime.now().date()
            
            # أ. تحديث بيانات المتوفى
            deceased.name = deceased_name
            deceased.national_id = deceased_nid
            deceased.account_number = self.detail_deceased_account_number_2.text().strip() or None
            deceased.archives_number = self.detail_deceased_archives_number_2.text().strip() or None
            
            death_date_text = try_get_date(self.detail_deceased_date_death_2.text().strip())
            deceased.date_death = parse_and_validate_date(death_date_text)

            # ب. تحديث/إنشاء كائن الوصي
            # guardian_obj = db.query(Guardian).filter_by(national_id=guardian_id).first()
            # if not guardian_obj:
            #     guardian_obj = Guardian(name=guardian_name, national_id=guardian_id, 
            #                             phone=self.detail_guardian_phone_2.text().strip() or None)
            #     db.add(guardian_obj)
            #     db.flush()
            # else:
            #     guardian_obj.name = guardian_name
            #     guardian_obj.phone = self.detail_guardian_phone_2.text().strip() or None

            # ج. معالجة الأيتام والروابط
            # g_start_text = self.detail_guardian_start_date_2.text().strip()
            # g_start_date = qdate_to_date(validate_date(g_start_text, False)) if g_start_text else today

            for odata in orphans_data:
                orphan_obj = None
                if odata.get('id'):
                    orphan_obj = db.query(Orphan).get(odata['id'])
                else:
                    filters = []
                    filters.append(Orphan.name == odata['name'])
                    if odata['national_id']:
                        filters.append(Orphan.national_id == odata['national_id'])
                    if filters:
                        orphan_obj = db.query(Orphan).filter(Orphan.id != odata['id'], or_(*filters)).first()
                    
                    if orphan_obj:
                        raise ValueError('الإسم أو رقم الهوية لليتيم مسجل مسبقاً في النظام')

                # إنشاء يتيم جديد إذا لزم الأمر
                if not orphan_obj:
                    orphan_obj = Orphan(deceased_id=deceased.id, name=odata['name'], 
                                        national_id=odata['national_id'], date_birth=odata['date_birth'], 
                                        gender=odata['gender'])
                    db.add(orphan_obj)
                    db.flush()
                    # إنشاء أرصدة (كما في دوالك السابقة)
                    balances = {'ILS': odata.get('ils_balance', 0), 'USD': odata.get('usd_balance', 0),
                                'JOD': odata.get('jod_balance', 0), 'EUR': odata.get('eur_balance', 0)}
                    self.db_service._create_opening_balances(db, orphan_obj.id, balances, True)
                else:
                    orphan_obj.deceased_id = deceased.id # تأكيد الارتباط بالمتوفى
                
                # --- تطبيق قاعدة الوصي الأساسي من الجدول ---
                orphan_ids = [o.id for o in deceased.orphans]
                if (not odata['id']) or (odata['id'] and (not odata['id'] in orphan_ids)):
                    row_g_id = odata.get('guardian_national_id') # تأكد أن المفتاح مطابق لما في get_orphans_table_data
                    row_g_name = odata.get('guardian_name')
                    # 1. البحث عن الوصي الجديد في القاعدة
                    if (row_g_id or row_g_name):
                        guardian_obj = None
                        
                        filters = []
                        filters.append(Guardian.name == row_g_name)
                        if row_g_id:
                            filters.append(Guardian.national_id == row_g_id)
                        if filters:
                            guardian_obj = db.query(Guardian).filter(or_(*filters)).first()
                        if not guardian_obj:
                            raise ValueError(f"الوصي غير موجود في النظام")
                    

                        # 2. خطوة "إنهاء القديم": أي وصي أساسي آخر لهذا اليتيم يصبح غير أساسي وينتهي اليوم
                        db.query(OrphanGuardian).filter(
                            OrphanGuardian.orphan_id == orphan_obj.id,
                            OrphanGuardian.guardian_id != guardian_obj.id,
                            OrphanGuardian.is_primary == True
                        ).update({
                            OrphanGuardian.is_primary: False, 
                            OrphanGuardian.end_date: today
                        }, synchronize_session=False)

                        # 3. خطوة "تثبيت الجديد": إنشاء الرابط أو تحديثه إذا كان موجوداً
                        link = db.query(OrphanGuardian).filter_by(
                            orphan_id=orphan_obj.id, 
                            guardian_id=guardian_obj.id
                        ).first()

                        if not link:
                            db.add(OrphanGuardian(
                                orphan_id=orphan_obj.id, 
                                guardian_id=guardian_obj.id,
                                is_primary=True, 
                                relation=odata.get('relation'), 
                                start_date=today
                            ))
                        else:
                            # إعادة تفعيل الرابط إذا كان موجوداً سابقاً
                            link.is_primary = True
                            link.relation = odata.get('relation')
                            link.start_date = today
                            link.end_date = None
                    else:
                        raise ValueError('يرجى ادخال إسم أو رقم هوية وصي مسجل مسبقاً في النظام لتعيينه كوصي أساسي لهذا اليتيم')
                
                #     # 4. في حال مسح رقم الهوية من الجدول: ننهي الوصاية الحالية (اختياري حسب رغبتك)
                #     db.query(OrphanGuardian).filter(
                #         OrphanGuardian.orphan_id == orphan_obj.id,
                #         OrphanGuardian.is_primary == True
                #     ).update({
                #         OrphanGuardian.is_primary: False, 
                #         OrphanGuardian.end_date: today
                #     }, synchronize_session=False)

                # --- تطبيق قاعدة الوصي الأساسي الوحيد ---
                # إنهاء وصاية الأوصياء الآخرين
                # db.query(OrphanGuardian).filter(
                #     OrphanGuardian.orphan_id == orphan_obj.id,
                #     OrphanGuardian.guardian_id != guardian_obj.id,
                #     OrphanGuardian.is_primary == True
                # ).update({OrphanGuardian.is_primary: False, OrphanGuardian.end_date: today}, synchronize_session=False)

                # # تحديث أو إنشاء رابط الوصي الجديد
                # link = db.query(OrphanGuardian).filter_by(orphan_id=orphan_obj.id, guardian_id=guardian_obj.id).first()
                # if not link:
                #     db.add(OrphanGuardian(orphan_id=orphan_obj.id, guardian_id=guardian_obj.id, 
                #                         is_primary=True, relation=guardian_kinship, start_date=g_start_date))
                # else:
                #     link.is_primary = True
                #     link.relation = guardian_kinship
                #     link.start_date = g_start_date
                #     link.end_date = None

            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.UPDATE, ResourceTypes.DECEASED, resource_id=deceased.id, description=f"تم تعديل سجل المتوفى: {deceased.name}.")
            self.statusBar().showMessage("تم تحديث البيانات بنجاح", 8000)
            self.open_person(deceased, PersonType.DECEASED)

        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "خطأ في البيانات", str(ve))
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ في النظام", f"حدث خطأ غير متوقع: {str(e)}")

    def save_person_record(self, obj):
        db = self.db_service.session
        try:
            if self.controller.current_type == PersonType.ORPHAN:
                self._save_orphan_record(db, obj)
                
            elif self.controller.current_type == PersonType.GUARDIAN:
                self._save_guardian_record(db, obj)

            elif self.controller.current_type == PersonType.DECEASED:
                self._save_deceased_record(db, obj)

        except Exception as e:
            print(f"Error saving person record: {e}")
            db.rollback()
            QMessageBox.warning(self, "خطأ", str(e))

    # ==== Lists Tabs ====
    def load_deceased_people_list(self):
        try:
            data = self.db_service.get_deceased_people_list()

            table = self.deceased_people_table
            table.setRowCount(len(data))

            for row_idx, (d, orphans_count) in enumerate(data):
                table.setItem(row_idx, 0, QTableWidgetItem(str(d.id)))
                table.setItem(row_idx, 1, QTableWidgetItem(d.name))
                table.setItem(row_idx, 2, QTableWidgetItem(d.national_id or "---"))
                table.setItem(row_idx, 3, QTableWidgetItem(
                    d.date_death.strftime("%d/%m/%Y") if d.date_death else "---"
                ))
                table.setItem(row_idx, 4, QTableWidgetItem(d.account_number or '---'))
                table.setItem(row_idx, 5, QTableWidgetItem(d.archives_number or '---'))
                table.setItem(row_idx, 6, QTableWidgetItem(str(orphans_count)))

        except Exception as e:
            print(f"Error loading deceased people: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات المتوفين:\n{str(e)}")
    
    def load_guardians_list(self):
        try:
            guardians_data = self.db_service.get_guardians_list()
            
            table = self.guardians_table
            table.setRowCount(0) # Clear existing rows
            
            for row_num, (guardian, orphan_count) in enumerate(guardians_data):
                table.insertRow(row_num)
                
                # ID
                table.setItem(row_num, 0, QTableWidgetItem(str(guardian.id)))
                # Name
                table.setItem(row_num, 1, QTableWidgetItem(guardian.name))
                # National ID
                table.setItem(row_num, 2, QTableWidgetItem(guardian.national_id or "---"))
                # Phone Number
                table.setItem(row_num, 3, QTableWidgetItem(guardian.phone or "---"))
                # Orphan Count
                table.setItem(row_num, 4, QTableWidgetItem(str(orphan_count)))
                
        except Exception as e:
            print(f"Error loading guardians list: {e}")
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء تحميل بيانات الأوصياء:\n{e}")
    
    def load_orphans_list(self):
        try:
            orphans = self.db_service.get_orphans_list()

            table = self.orphans_table
            table.setRowCount(len(orphans))

            for row_idx, orphan in enumerate(orphans):
                table.setItem(row_idx, 0, QTableWidgetItem(str(orphan.id)))
                table.setItem(row_idx, 1, QTableWidgetItem(orphan.name))
                table.setItem(row_idx, 2, QTableWidgetItem(orphan.national_id or "---"))
                table.setItem(row_idx, 3, QTableWidgetItem(
                    orphan.date_birth.strftime("%d/%m/%Y")
                    if orphan.date_birth else "---"
                ))
                gender_str = "ذكر" if orphan.gender.value == 1 else "أنثى"
                table.setItem(row_idx, 4, QTableWidgetItem(gender_str))
                
                table.setItem(row_idx, 5, QTableWidgetItem(str(orphan.age)))
                
                primary_guardian = next(
                    (link.guardian for link in orphan.guardian_links if link.is_primary),
                    None
                )

                guardian_name = primary_guardian.name if primary_guardian else "---"
                table.setItem(row_idx, 6, QTableWidgetItem(guardian_name))

        except Exception as e:
            print(f"Error loading all orphans: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات الأيتام:\n{str(e)}")

    def load_orphans_older_than_or_equal_18_list(self):
        try:
            orphans = self.db_service.get_orphans_older_than_or_equal_18_list()

            table = self.orphans_older_or_equal_18_table
            table.setRowCount(len(orphans))

            for row_idx, orphan in enumerate(orphans):
                table.setItem(row_idx, 0, QTableWidgetItem(str(orphan.id)))
                table.setItem(row_idx, 1, QTableWidgetItem(orphan.name))
                table.setItem(row_idx, 2, QTableWidgetItem(orphan.national_id or "---"))
                table.setItem(row_idx, 3, QTableWidgetItem(
                    orphan.date_birth.strftime("%d/%m/%Y") if orphan.date_birth else "---"
                ))
                gender_str = "ذكر" if orphan.gender.value == 1 else "أنثى"
                table.setItem(row_idx, 4, QTableWidgetItem(gender_str))
                table.setItem(row_idx, 5, QTableWidgetItem(str(orphan.age)))

        except Exception as e:
            print(f"Error loading orphans older than or equal 18: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات الأيتام الأكبر من 18 سنة:\n{str(e)}")

    # ==== Pagination Tables ====
    def load_table_paginated(self, table, pagination, pagination_label, fetch_func, row_renderer):
        result = fetch_func(pagination.page, pagination.per_page)

        pagination.update(result)

        items = result["items"]
        table.setRowCount(len(items))

        for row, item in enumerate(items):
            row_renderer(table, row, item)

        self.update_pagination_label(pagination, pagination_label)
    
    def render_deceased_row(self, table, row, data):
        d, orphans_count = data
        table.setItem(row, 0, QTableWidgetItem(str(d.id)))
        table.setItem(row, 1, QTableWidgetItem(d.name))
        table.setItem(row, 2, QTableWidgetItem(d.national_id or "---"))
        table.setItem(row, 3, QTableWidgetItem(
            d.date_death.strftime("%d/%m/%Y") if d.date_death else "---"
        ))
        table.setItem(row, 4, QTableWidgetItem(d.account_number or "---"))
        table.setItem(row, 5, QTableWidgetItem(d.archives_number or "---"))
        table.setItem(row, 6, QTableWidgetItem(str(orphans_count)))
    
    def render_guardian_row(self, table, row, data):
        guardian, orphan_count = data
        table.setItem(row, 0, QTableWidgetItem(str(guardian.id)))
        table.setItem(row, 1, QTableWidgetItem(guardian.name))
        table.setItem(row, 2, QTableWidgetItem(guardian.national_id or '---'))
        table.setItem(row, 3, QTableWidgetItem(guardian.phone or "---"))
        table.setItem(row, 4, QTableWidgetItem(str(orphan_count)))
    
    def render_orphan_row(self, table, row, orphan):
        table.setItem(row, 0, QTableWidgetItem(str(orphan.id)))
        table.setItem(row, 1, QTableWidgetItem(orphan.name))
        table.setItem(row, 2, QTableWidgetItem(orphan.national_id or "---"))
        table.setItem(row, 3, QTableWidgetItem(
            orphan.date_birth.strftime("%d/%m/%Y") if orphan.date_birth else "---"
        ))
        gender_str = "ذكر" if orphan.gender.value == 1 else "أنثى"
        table.setItem(row, 4, QTableWidgetItem(gender_str))
        table.setItem(row, 5, QTableWidgetItem(str(orphan.age)))

        primary_guardian = next(
            (l.guardian for l in orphan.guardian_links if l.is_primary),
            None
        )
        table.setItem(row, 6, QTableWidgetItem(
            primary_guardian.name if primary_guardian else "---"
        ))
    
    def render_orphan_older_equal_18_row(self, table, row, orphan):
        table.setItem(row, 0, QTableWidgetItem(str(orphan.id)))
        table.setItem(row, 1, QTableWidgetItem(orphan.name))
        table.setItem(row, 2, QTableWidgetItem(orphan.national_id or "---"))
        table.setItem(row, 3, QTableWidgetItem(
            orphan.date_birth.strftime("%d/%m/%Y") if orphan.date_birth else "---"
        ))
        gender_str = "ذكر" if orphan.gender.value == 1 else "أنثى"
        table.setItem(row, 4, QTableWidgetItem(gender_str))
        table.setItem(row, 5, QTableWidgetItem(str(orphan.age)))

    def render_activity_log_row(self, table, row, activity):
        formatted_date = activity.created_at.strftime("%Y-%m-%d %H:%M")
        
        # تحويل العملية للعربية
        action = activity.action.lower()
        ar_action = {"delete": "حذف", "create": "إنشاء", "update": "تعديل"}.get(action, action)

        # --- التعديل هنا: تحويل نوع المورد للعربية ---
        # نستخدم .get لجلب القيمة العربية، وإذا لم توجد نضع النص الأصلي
        ar_resource = ar_resource_types.get(activity.resource_type, activity.resource_type)
        
        # إضافة الخلايا
        table.setItem(row, 0, self._create_readonly_item(str(activity.id)))
        table.setItem(row, 1, self._create_readonly_item(formatted_date))
        table.setItem(row, 2, self._create_readonly_item(activity.user.username))
        table.setItem(row, 3, self._create_readonly_item(ar_action))
        table.setItem(row, 4, self._create_readonly_item(ar_resource)) # عرض الاسم العربي
        table.setItem(row, 5, self._create_readonly_item(activity.description))
        
        if action == "delete":
            table.item(row, 3).setForeground(Qt.GlobalColor.red)
        elif action == "create":
            table.item(row, 3).setForeground(Qt.GlobalColor.darkGreen)
        elif action == "update":
            table.item(row, 3).setForeground(Qt.GlobalColor.darkBlue)
        else:
            table.item(row, 3).setForeground(Qt.GlobalColor.black)

    def update_pagination_label(self, pagination, pagination_label):
        # Use pagination object to compute pages and current page for the label
        pages = getattr(pagination, 'pages', None)
        if pages is None:
            total = getattr(pagination, 'total', 0)
            per = getattr(pagination, 'per_page', 1)
            pages = max(1, math.ceil(total / per)) if per else 1
        current = getattr(pagination, 'page', 1)
        pagination_label.setText(f"الصفحة {current} من {pages}")

    def next_page(self, pagination=None):
        # If this method is connected directly to a button click, Qt will pass
        # a boolean `checked` argument. Handle that by inferring which
        # pagination controller to use based on the currently active main tab.
        if isinstance(pagination, bool) or pagination is None:
            tab = self.tabWidget.currentIndex()
            if tab == 3:
                pagination = self.deceased_pagination
            elif tab == 4:
                pagination = self.guardians_pagination
            elif tab == 5:
                pagination = self.orphans_pagination
            elif tab == 6:
                pagination = self.orphans_older_or_equal_18_pagination
            elif tab == 10:
                pagination = self.activity_log_pagination
            else:
                return
        pagination.next()
        self.reload_current_tab()

    def prev_page(self, pagination=None):
        if isinstance(pagination, bool) or pagination is None:
            tab = self.tabWidget.currentIndex()
            if tab == 3:
                pagination = self.deceased_pagination
            elif tab == 4:
                pagination = self.guardians_pagination
            elif tab == 5:
                pagination = self.orphans_pagination
            elif tab == 6:
                pagination = self.orphans_older_or_equal_18_pagination
            elif tab == 10:
                pagination = self.activity_log_pagination
            else:
                return
        pagination.prev()
        self.reload_current_tab()

    def reload_current_tab(self):
        tab = self.tabWidget.currentIndex()
        # Deceased (index 3) - paginated
        if tab == 3:
            self.load_table_paginated(
                self.deceased_people_table,
                self.deceased_pagination,
                self.pagination_label,
                self.db_service.get_deceased_people_paginated,
                self.render_deceased_row,
            )
        # Guardians (index 4) - prefer paginated fetcher, fallback to non-paginated loader
        elif tab == 4:
            try:
                self.load_table_paginated(
                    self.guardians_table,
                    self.guardians_pagination,
                    self.pagination_label_2,
                    self.db_service.get_guardians_paginated,
                    self.render_guardian_row,
                )
            except Exception:
                self.load_guardians_list()
        # Orphans (index 5) - paginated
        elif tab == 5:
            try:
                self.load_table_paginated(
                    self.orphans_table,
                    self.orphans_pagination,
                    self.pagination_label_3,
                    self.db_service.get_orphans_paginated,
                    lambda table, row, orphan: self.render_orphan_row(table, row, orphan),
                )
            except Exception:
                self.load_orphans_list()
        # Orphans older than or equal to 18 (index 6) - non-paginated
        elif tab == 6:
            try:
                self.load_table_paginated(
                    self.orphans_older_or_equal_18_table,
                    self.orphans_older_or_equal_18_pagination,
                    self.pagination_label_4,
                    self.db_service.get_orphans_older_than_or_equal_18_paginated,
                    lambda table, row, orphan: self.render_orphan_older_equal_18_row(table, row, orphan)
                )
            except Exception:
                self.load_orphans_older_than_or_equal_18_list()
        elif tab == 10:
            # try:
                self.load_table_paginated(
                    self.activity_logs_table,
                    self.activity_log_pagination,
                    self.pagination_label_5,
                    self.db_service.get_activity_logs_paginated,
                    lambda table, row, activity: self.render_activity_log_row(table, row, activity),
                )
            # except Exception:
            #     self.load_activity_log_list()
        else:
            # No paginated content on other tabs
            pass

    # ==== User Tab Methods ====
    # دالة لتبديل تفعيل الحقول قبل البحث الحقول غير مفعلة بعد البحث الحقول تتفعل
    
    def toggle_user_inputs(self, is_enabled):
        self.role_comboBox_2.setEnabled(is_enabled)
        self.super_user_checkBox_2.setEnabled(is_enabled)
        self.lineEdit_5.setEnabled(is_enabled)
        self.lineEdit_7.setEnabled(is_enabled)
        self.lineEdit_8.setEnabled(is_enabled)
        self.pushButton_2.setEnabled(is_enabled)
    
    def clear_user_inputs(self):
        self.load_roles_combo(self.role_comboBox_2)
        self.super_user_checkBox_2.setChecked(False)
        self.lineEdit_5.clear()
        self.lineEdit_6.clear()
        self.lineEdit_7.clear()
        self.lineEdit_8.clear()
        self.user_id_input.clear()
        self.toggle_user_inputs(False)
    
    def create_user(self):
        db = self.db_service.session
        
        users = db.query(User).all()
        if len(users) > 5: 
            QMessageBox.critical(self, 'خطأ', 'لقد تجاوزت الحد المسموح به')
            return
        
        try:
            # 1. سحب البيانات وتجهيزها
            name = self.lineEdit.text().strip()
            username = self.lineEdit_2.text().strip()
            password = self.lineEdit_3.text().strip()
            password_2 = self.lineEdit_4.text().strip()
            role_id = self.role_comboBox.currentData()  # يجب أن يكون comboBox مرتبط بالـ role.id
            is_superuser = self.super_user_checkBox.isChecked()  # Checkbox يعطي True/False

            # 2. التحقق من الحقول الفارغة
            if not all([name, username, password, password_2]):
                raise ValueError('جميع الحقول مطلوبة')

            if password != password_2:
                raise ValueError('كلمتا المرور غير متطابقة')

            # 3. التحقق من وجود المستخدم مسبقاً
            existing_user = db.query(User).filter_by(username=username).first()
            if existing_user:
                raise ValueError('اسم المستخدم هذا موجود بالفعل')

            # 4. تشفير كلمة المرور
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            # 5. إنشاء المستخدم مع الدور و is_superuser
            new_user = User(
                name=name,
                username=username,
                password=hashed_password,
                is_superuser=is_superuser,
                role_id=role_id
            )

            db.add(new_user)
            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.CREATE, ResourceTypes.USER, resource_id=new_user.id, description=f"تم إنشاء حساب المستخدم: {username}.")
            QMessageBox.information(self, "نجاح", "تم إنشاء الحساب بنجاح!")
            # تنظيف الحقول
            self.lineEdit.clear()
            self.lineEdit_2.clear()
            self.lineEdit_3.clear()
            self.lineEdit_4.clear()
            self.role_comboBox.setCurrentIndex(0)
            self.super_user_checkBox.setChecked(False)

        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ في النظام", f"حدث خطأ غير متوقع: {str(e)}")
    
    def show_user_detail(self):
        db = self.db_service.session
        try:
            username = self.lineEdit_6.text().strip()
            if not username:
                raise ValueError('الرجاء إدخال إسم المستخدم')
            
            user = db.query(User).filter_by(username=username).first()
            if not user:
                self.user_id_input.clear()
                self.lineEdit_5.clear()
                self.load_roles_combo(self.role_comboBox_2)
                self.super_user_checkBox_2.setChecked(False)
                self.lineEdit_7.clear()
                self.lineEdit_8.clear()
                self.toggle_user_inputs(False)
                raise ValueError('اسم المستخدم هذا غير موجود')
            
            self.toggle_user_inputs(True)
            self.user_id_input.setText(str(user.id))
            self.lineEdit_5.setText(user.name)
            if user.role_id:
                index = self.role_comboBox_2.findData(user.role_id)
                if index >= 0:
                    self.role_comboBox_2.setCurrentIndex(index)
            else:
                self.role_comboBox_2.setCurrentIndex(0)  # افتراضي

            # تعيين حالة superuser
            self.super_user_checkBox_2.setChecked(user.is_superuser)
        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"حدث خطأ غير متوقع: {str(e)}")

    def update_user(self):
        db = self.db_service.session
        try:
            user_id = self.user_id_input.text().strip()
            username = self.lineEdit_6.text().strip()
            name = self.lineEdit_5.text().strip()
            password = self.lineEdit_7.text().strip()
            password_2 = self.lineEdit_8.text().strip()
            role_id = self.role_comboBox_2.currentData()
            is_superuser = self.super_user_checkBox_2.isChecked()

            if not username or not name:
                raise ValueError('حقول الإسم واسم المستخدم مطلوبة')

            user = db.query(User).get(user_id)
            if not user:
                raise ValueError('لم يتم العثور على اسم المستخدم المحدد')

            # تحديث البيانات
            # تحديث اسم المستخدم فقط إذا تم تغييره وإلا قد يحدث تعارض مع اسم مستخدم آخر
            if user.username != username:
                if db.query(User).filter(User.username == username, User.id != user.id).first():
                    raise ValueError('اسم المستخدم هذا موجود بالفعل')
                user.username = username
            user.name = name
            user.role_id = role_id
            user.is_superuser = is_superuser

            # تحديث كلمة المرور فقط إذا تم إدخالها
            if password or password_2:
                if password != password_2:
                    raise ValueError('كلمتا المرور غير متطابقة')
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                user.password = hashed

            db.commit()
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.UPDATE, ResourceTypes.USER, resource_id=user.id, description=f"تم تعديل بيانات المستخدم: {username}.")
            # self.statusBar().showMessage("تم تحديث بيانات المستخدم بنجاح", 8000)
            QMessageBox.information(self, "نجاح", "تم تحديث بيانات المستخدم بنجاح")
            self.clear_user_update_btn.click()
            self.toggle_user_inputs(False)
            self.check_permissions()
        except ValueError as ve:
            db.rollback()
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"حدث خطأ غير متوقع: {str(e)}")
    
    def logout(self):
        reply = QMessageBox.question(self, 'خروج', "هل أنت متأكد من تسجيل الخروج؟", 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # إعادة تشغيل التطبيق
            os.execl(sys.executable, sys.executable, *sys.argv)
    
    def delete_user(self):
        pass
    
    # ==== Roles Tab Methods ====
    def load_roles(self):
        db = self.db_service.session
        roles = db.query(Role).all()
        table = self.roles_table
        table.setRowCount(len(roles))
        for row_idx, role in enumerate(roles):
            table.setItem(row_idx, 0, self._create_readonly_item(str(role.id)))
            table.setItem(row_idx, 1, self._create_readonly_item(role.name))

    def save_role(self):
        try:
            role_id = self.role_id_input.text().strip()
            role_name = self.role_name_input.text().strip()

            if not role_name:
                raise ValueError('حقل الإسم مطلوب.')

            db = self.db_service.session

            # التحقق من عدم وجود اسم دور مكرر
            existing_role = db.query(Role).filter(Role.name == role_name)
            if role_id:
                existing_role = existing_role.filter(Role.id != int(role_id))
            if existing_role.first():
                raise ValueError('اسم الدور موجود بالفعل.')

            if role_id:
                # تعديل الدور
                role = db.query(Role).filter_by(id=role_id).first()
                if not role:
                    raise ValueError('الدور غير موجود!')
                role.name = role_name
                db.commit()
                QMessageBox.information(self, "نجاح", f"تم تعديل الدور '{role_name}' بنجاح!")
            else:
                # إنشاء دور جديد
                new_role = Role(name=role_name)
                db.add(new_role)
                db.commit()
                QMessageBox.information(self, "نجاح", f"تم إضافة الدور '{role_name}' بنجاح!")

            log_activity(self.db_service.session, self.current_user.id, ActionTypes.CREATE if not role_id else ActionTypes.UPDATE, ResourceTypes.ROLE, resource_id=new_role.id if not role_id else int(role_id), description=f"تم حفظ/تعديل الدور: {role_name}.")
            # مسح الحقول وإعادة تحميل الأدوار
            self.role_id_input.clear()
            self.role_name_input.clear()
            self.load_roles()

        except ValueError as ve:
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ غير متوقع: {str(e)}")

    def delete_role(self):
        try:
            role_id = self.role_id_input.text().strip()
            role_name = self.role_name_input.text().strip()

            if not role_id:
                QMessageBox.warning(self, "تنبيه", "الرجاء إدخال معرف الدور.")
                return

            # تأكيد الحذف
            reply = QMessageBox.question(
                self,
                "تأكيد الحذف",
                f"هل أنت متأكد من حذف الدور '{role_name}'؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return  # تم الإلغاء

            db = self.db_service.session
            role = db.query(Role).filter_by(id=role_id).first()

            if not role:
                QMessageBox.warning(self, "تنبيه", "الدور غير موجود!")
                return

            db.delete(role)
            db.commit()

            log_activity(self.db_service.session, self.current_user.id, ActionTypes.DELETE, ResourceTypes.ROLE, resource_id=role.id, description=f"تم حذف الدور: {role_name}.")
            self.role_id_input.clear()
            self.role_name_input.clear()
            QMessageBox.information(self, "نجاح", "تم حذف الدور بنجاح!")
            self.load_roles()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ غير متوقع: {str(e)}")

    def on_role_row_clicked(self, row, column):
        role_id_item = self.roles_table.item(row, 0)  # عمود ID
        role_name_item = self.roles_table.item(row, 1)  # عمود الاسم
        
        if role_id_item and role_name_item:
            self.role_id_input.setText(role_id_item.text())
            self.role_name_input.setText(role_name_item.text())
    
    # ==== Permissions Tab Methods ====
    def load_roles_combo(self, comboBox: QComboBox):
        comboBox.clear()

        db = self.db_service.session
        roles = db.query(Role).order_by(Role.name).all()

        # عنصر افتراضي
        comboBox.addItem("اختر الدور", None)

        for role in roles:
            comboBox.addItem(role.name, role.id)
    
    def get_checkbox_from_cell(self, row, col):
        container = self.permissions_table.cellWidget(row, col)
        if not container:
            return None
        # البحث عن الـ CheckBox داخل الحاوية باستخدام الاسم الذي وضعناه
        return container.findChild(QCheckBox, "perm_check")
    
    def load_permissions(self):
        role_id = self.roles_combo.currentData()
        if not role_id:
            self.permissions_table.setRowCount(0)
            return

        db = self.db_service.session
        permissions = db.query(Permission).all()
        
        role_permissions = db.query(RolePermission.permission_id)\
            .filter(RolePermission.role_id == role_id).all()
        role_permission_ids = {p[0] for p in role_permissions}

        # --- الإصلاح هنا: معالجة الـ Enum ---
        RESOURCE_AR = {
            "Home": "الصفحة الرئيسية",
            "PersonDetail": "سجل الشخص",
            "NewPerson": "سجل جديد",
            "DeceasedList": "المتوفون",
            "GuardiansList": "الأوصياء الشرعيون ",
            "OrphansList": "الأيتام",
            "OrphansOver18": "الأيتام فوق 18 سنة",
            "Users": "المستخدمون",
            "Roles": "الأدوار",
            "Permissions": "الصلاحيات",
            "Settings": "الإعدادات",
            "Reports": "التقارير",
            "Transactions": "الحركات المالية",
            "Balances": "الأرصدة",
            "Currencies": "العملات",
            "ActivityLogs": "سجل النشاطات",
        }

        resources = {}
        for p in permissions:
            if p.resource not in resources:
                resources[p.resource] = {'view': None, 'create': None, 'update': None, 'delete': None}
            
            # استخراج اسم الفعل من الـ Enum (مثلاً نأخذ 'view' من 'PermissionEnum.view')
            action_str = p.action.value if hasattr(p.action, 'value') else str(p.action)
            action_str = action_str.split('.')[-1].lower()
            
            if action_str in resources[p.resource]:
                resources[p.resource][action_str] = p

        self.permissions_table.setRowCount(len(resources))

        for row, (resource_name, actions) in enumerate(resources.items()):
            arabic_name = RESOURCE_AR.get(resource_name, resource_name)
            item = QTableWidgetItem(arabic_name)
            self.permissions_table.setItem(row, 0, item)

            for col, action_key in enumerate(['view', 'create', 'update', 'delete'], start=1):
                perm = actions.get(action_key)
                
                container = QWidget()
                layout = QHBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                if perm:
                    chk = QCheckBox()
                    chk.setObjectName("perm_check")
                    # تخزين الـ ID كـ int صريح
                    chk.setProperty("perm_id", int(perm.id))
                    
                    if perm.id in role_permission_ids:
                        chk.setChecked(True)
                    
                    layout.addWidget(chk)
                
                self.permissions_table.setCellWidget(row, col, container)

    def save_permissions(self):
        role_id = self.roles_combo.currentData()
        if not role_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار دور")
            return

        db = self.db_service.session
        try:
            # 1. حذف الصلاحيات القديمة لهذا الدور
            db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()

            # 2. قراءة الجدول وحفظ المربعات المحددة
            count = 0
            for row in range(self.permissions_table.rowCount()):
                for col in range(1, 5): # من العمود 1 إلى 4
                    chk = self.get_checkbox_from_cell(row, col)
                    
                    if chk and chk.isChecked():
                        p_id = chk.property("perm_id")
                        if p_id:
                            db.add(RolePermission(role_id=role_id, permission_id=int(p_id)))
                            count += 1

            db.commit()
            role = db.query(Role).get(role_id)
            log_activity(self.db_service.session, self.current_user.id, ActionTypes.UPDATE, ResourceTypes.PERMISSION, description=f"تم حفظ الصلاحيات للدور : {role.name}.")
            print(f"Successfully saved {count} permissions.")
            QMessageBox.information(self, "نجاح", f"تم حفظ {count} من الصلاحيات بنجاح")
            self.check_permissions()
            if not has_permission(self.current_user, 'Permissions', PermissionEnum.view):
                self.set_sellected_list_item(self.listWidget, 0)

        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "خطأ", f"فشل الحفظ: {str(e)}")

    def check_all(self):
        for row in range(self.permissions_table.rowCount()):
            for col in range(1, self.permissions_table.columnCount()):
                chk = self.get_checkbox_from_cell(row, col)
                if chk:
                    chk.setChecked(True)
    
    def uncheck_all(self):
        for row in range(self.permissions_table.rowCount()):
            for col in range(1, self.permissions_table.columnCount()):
                chk = self.get_checkbox_from_cell(row, col)
                if chk:
                    chk.setChecked(False)
    
    # ==== Reports Export Methods ====
    def open_export_popup(self):
        dialog = ExportReportDialog(self)
        if dialog.exec(): # إذا ضغط المستخدم على "تصدير الآن"
            print("تمت عملية التصدير بنجاح")
    
    def export_person_record(self, obj):
        try:
            if not obj:
                QMessageBox.warning(self, "تنبيه", "يرجى اختيار سجل أولاً.")
                return

            # تحديد النوع والاسم الافتراضي بناءً على الاختيار
            if self.controller.current_type == PersonType.ORPHAN:
                entity_type = "orphan"
            elif self.controller.current_type == PersonType.GUARDIAN:
                entity_type = "guardian"
            elif self.controller.current_type == PersonType.DECEASED:
                entity_type = "deceased"
            else:
                return

            default_name = f"تقرير_{entity_type}_{obj.id}_{date.today().strftime('%Y%m%d')}.pdf"
            path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير", default_name, "PDF Files (*.pdf)")
            
            if path:
                # استخدام obj.id مباشرة بدلاً من متغيرات خارجية
                generate_report(entity_type, obj.id, path, self.current_user)
                QMessageBox.information(self, "تم", f"تم حفظ التقرير بنجاح")
        except Exception as e:
            print(e)
            QMessageBox.critical(self, "خطأ", f"فشل التصدير: {str(e)}")
    
    def toggle_deceased_ils_inputs(self):
        index = self.comboBox.currentIndex()
        # اسم البنك (ILS)
        self.label_146.hide()
        self.lineEdit_14.hide()
        self.lineEdit_14.clear()
        # رصيد الشيكل (شيك)
        self.label_143.hide()
        self.label_145.hide()
        self.lineEdit_12.hide()
        self.lineEdit_13.hide()
        self.lineEdit_12.clear()
        self.lineEdit_13.clear()
        # رقم الحوالة (شيكل)
        self.label_147.hide()
        self.lineEdit_15.hide()
        self.lineEdit_15.clear()
        if index == 1:
            # اسم البنك (ILS)
            self.label_146.show()
            self.lineEdit_14.show()
            # رصيد الشيكل (شيك)
            self.label_143.show()
            self.label_145.show()
            self.lineEdit_12.show()
            self.lineEdit_13.show()
        elif index == 2:
            # اسم البنك (ILS)
            self.label_146.show()
            self.lineEdit_14.show()
            # رقم الحوالة (شيكل)
            self.label_147.show()
            self.lineEdit_15.show()
    
    def toggle_deceased_usd_inputs(self):
        index = self.comboBox_2.currentIndex()
        # اسم البنك (USD)
        self.label_150.hide()
        self.lineEdit_19.hide()
        self.lineEdit_19.clear()
        # رصيد الدولار (شيك)
        self.label_149.hide()
        self.label_151.hide()
        self.lineEdit_17.hide()
        self.lineEdit_18.hide()
        self.lineEdit_17.clear()
        self.lineEdit_18.clear()
        # رقم الحوالة (دولار)
        self.label_152.hide()
        self.lineEdit_20.hide()
        self.lineEdit_20.clear()
        if index == 1:
            # اسم البنك (USD)
            self.label_150.show()
            self.lineEdit_19.show()
            # رصيد الدولار (شيك)
            self.label_149.show()
            self.label_151.show()
            self.lineEdit_17.show()
            self.lineEdit_18.show()
        elif index == 2:
            # اسم البنك (USD)
            self.label_150.show()
            self.lineEdit_19.show()
            # رقم الحوالة (دولار)
            self.label_152.show()
            self.lineEdit_20.show()
    
    def toggle_deceased_jod_inputs(self):
        index = self.comboBox_3.currentIndex()
        # اسم البنك (JOD)
        self.label_156.hide()
        self.lineEdit_26.hide()
        self.lineEdit_26.clear()

        # رصيد الدينار (شيك)
        self.label_155.hide()
        self.label_157.hide()
        self.lineEdit_24.hide()
        self.lineEdit_25.hide()
        self.lineEdit_24.clear()
        self.lineEdit_25.clear()

        # رقم الحوالة (دينار)
        self.label_158.hide()
        self.lineEdit_27.hide()
        self.lineEdit_27.clear()
        
        if index == 1:
            # اسم البنك (JOD)
            self.label_156.show()
            self.lineEdit_26.show()
            # رصيد الدينار (شيك)
            self.label_155.show()
            self.label_157.show()
            self.lineEdit_24.show()
            self.lineEdit_25.show()
        elif index == 2:
            # اسم البنك (JOD)
            self.label_156.show()
            self.lineEdit_26.show()
            # رقم الحوالة (دينار)
            self.label_158.show()
            self.lineEdit_27.show()
    
    def toggle_deceased_eur_inputs(self):
        index = self.comboBox_4.currentIndex()
        # اسم البنك (EUR)
        self.label_162.hide()
        self.lineEdit_33.hide()
        self.lineEdit_33.clear()

        # رصيد اليورو (شيك)
        self.label_161.hide()
        self.label_163.hide()
        self.lineEdit_31.hide()
        self.lineEdit_32.hide()
        self.lineEdit_31.clear()
        self.lineEdit_32.clear()

        # رقم الحوالة (يورو)
        self.label_164.hide()
        self.lineEdit_34.hide()
        self.lineEdit_34.clear()
        
        if index == 1:
            # اسم البنك (EUR)
            self.label_162.show()
            self.lineEdit_33.show()
            # رصيد اليورو (شيك)
            self.label_161.show()
            self.label_163.show()
            self.lineEdit_31.show()
            self.lineEdit_32.show()
        elif index == 2:
            # اسم البنك (EUR)
            self.label_162.show()
            self.lineEdit_33.show()
            # رقم الحوالة (يورو)
            self.label_164.show()
            self.lineEdit_34.show()
    
    def load_activity_log_list(self):
        table = self.activity_logs_table
        session = self.db_service.session
        logs = session.query(ActivityLog).join(User).order_by(ActivityLog.created_at.desc()).all()

        # 2. إعداد إعدادات الجدول الأساسية
        table.setRowCount(0)  # تفريغ الجدول قبل التحديث
        
        # 3. تعبئة البيانات
        for row_number, log in enumerate(logs):
            table.insertRow(row_number)
            
            # تنسيق التاريخ
            formatted_date = log.created_at.strftime("%Y-%m-%d %H:%M")
            
            # تحويل العملية للعربية
            action = log.action.lower()
            ar_action = {"delete": "حذف", "create": "إنشاء", "update": "تعديل"}.get(action, action)

            # --- التعديل هنا: تحويل نوع المورد للعربية ---
            # نستخدم .get لجلب القيمة العربية، وإذا لم توجد نضع النص الأصلي
            ar_resource = ar_resource_types.get(log.resource_type, log.resource_type)
            
            # إضافة الخلايا
            table.setItem(row_number, 0, self._create_readonly_item(str(log.id)))
            table.setItem(row_number, 1, self._create_readonly_item(formatted_date))
            table.setItem(row_number, 2, self._create_readonly_item(log.user.username))
            table.setItem(row_number, 3, self._create_readonly_item(ar_action))
            table.setItem(row_number, 4, self._create_readonly_item(ar_resource)) # عرض الاسم العربي
            table.setItem(row_number, 5, self._create_readonly_item(log.description))
            
            if action == "delete":
                table.item(row_number, 3).setForeground(Qt.GlobalColor.red)
            elif action == "create":
                table.item(row_number, 3).setForeground(Qt.GlobalColor.darkGreen)
            elif action == "update":
                table.item(row_number, 3).setForeground(Qt.GlobalColor.darkBlue)
            else:
                table.item(row_number, 3).setForeground(Qt.GlobalColor.black)

    def handle_logout(self):
        reply = QMessageBox.question(self, 'خروج', "هل أنت متأكد من تسجيل الخروج؟", 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.set_sellected_list_item(self.listWidget, 0)  # إعادة تعيين اختيار القائمة إلى الصفحة الرئيسية
            self.logout_signal.emit()
    
    def load_users_list(self):
        table = self.users_table
        session = self.db_service.session
        users = session.query(User).join(Role, isouter=True).order_by(User.id).all()

        table.setRowCount(0)  # تفريغ الجدول قبل التحديث

        for row_number, user in enumerate(users):
            table.insertRow(row_number)
            table.setItem(row_number, 0, self._create_readonly_item(str(user.id)))
            table.setItem(row_number, 1, self._create_readonly_item(user.name))
            table.setItem(row_number, 2, self._create_readonly_item(user.username))
            role_name = user.role.name if user.role else "---"
            table.setItem(row_number, 3, self._create_readonly_item(role_name))
            is_superuser_str = "نعم" if user.is_superuser else "لا"
            table.setItem(row_number, 4, self._create_readonly_item(is_superuser_str))
    
    def setup_balance_table(self, table_widget, data):
        """
        data: قائمة تحتوي على كائنات أو قواميس بالبيانات
        مثال: [('الشيكل', 100, 50, 50), ('الدولار', 200, 0, 200), ...]
        """
        # 1. إعداد العناوين (الأعمدة)
        headers = ["إجمالي المُودَع", "إجمالي المسحوب", "إجمالي المتاح"]
        table_widget.setColumnCount(3) # 3 أعمدة للبيانات
        table_widget.setHorizontalHeaderLabels(headers)
        
        # إعداد الصفوف (العملات)
        table_widget.setRowCount(len(data))
        
        # ضبط الاتجاه للعربية
        table_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        # 2. تعبئة البيانات
        for row_idx, (currency_name, deposited, withdrawn, available) in enumerate(data):
            
            # ضبط اسم العملة كـ Vertical Header (العنوان الجانبي كما في الصورة)
            header_item = QTableWidgetItem(currency_name)
            header_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            table_widget.setVerticalHeaderItem(row_idx, header_item)
            
            # تعبئة القيم في الأعمدة
            values = [deposited, withdrawn, available]
            for col_idx, value in enumerate(values):
                # تنسيق الرقم (مثلاً 1,250.00)
                formatted_value = "{:,.2f}".format(float(value)) if value else "0.00"
                item = QTableWidgetItem(formatted_value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # تمييز عمود "المتاح" باللون أو الخط العريض
                if col_idx == 2: # عمود المتاح
                    # item.setForeground(QColor("#2ecc71")) # لون أخضر غامق مثلاً
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    
                table_widget.setItem(row_idx, col_idx, item)

        # 3. تحسين المظهر
        # جعل عرض عنوان العملة الجانبي ثابتاً ومناسباً
        table_widget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_widget.verticalHeader().setFixedWidth(120) 
        
        # جعل الأعمدة تتمدد بالتساوي
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    
    def on_deceased_selected(self, index):
        # الحصول على الـ ID المخفي الذي خزناه في addItem
        deceased_id = self.d_combo.itemData(index)
        if deceased_id:
            print(f"تم اختيار المتوفى صاحب الرقم التسلسلي: {deceased_id}")
    
    # ===== Close Event =====
    def closeEvent(self, event):
        self.db_service.close()
        event.accept()

# ===== Main =====
def main():
    app = QApplication(sys.argv)
    
    translator = QTranslator()
    qt_translator = QTranslator()
    translator_path = resource_path(os.path.join("locale", "ar", "qt_ar.qm"))
    translator.load(translator_path)
    qt_translator.load(
        "qt_ar",
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    )
    app.installTranslator(translator)
    app.installTranslator(qt_translator)

    # تحميل style.qss بشكل محسّن (استخدام try/except لتقليل البطء)
    style_path = resource_path(os.path.join("assets", "style.qss"))
    
    try:
        with open(style_path, "r", encoding="utf-8") as f:
            stylesheet = f.read()
            # تطبيق الستايل بشكل فوري وإجمالي بدل التطبيق المتدرج
            app.setStyleSheet(stylesheet)
    except FileNotFoundError:
        logger.error(f"Could not find style file at: {style_path}")
    except Exception as e:
        logger.warning(f"Error loading stylesheet: {e}")

    # عرض معلومات البدء
    # logger.info(f"=" * 50)
    # logger.info(f"جاري بدء التطبيق...")
    # logger.info(f"نوع قاعدة البيانات: {DATABASE_TYPE}")
    # logger.info(f"=" * 50)
    
    # تهيئة قاعدة البيانات (بدون تحميل الخطوط في exe)
    db = DBService()
    
    # إنشاء نافذة تسجيل الدخول فقط في البداية (أسرع)
    login_win = LoginWindow(db)
    
    # سيتم تأجيل إنشاء MainWindow إلى ما بعد نجاح تسجيل الدخول
    main_win = None

    # --- عند نجاح تسجيل الدخول ---
    def on_login_success(user):
        nonlocal main_win
        
        # إنشاء MainWindow فقط بعد تسجيل الدخول (أسرع تجربة)
        if main_win is None:
            logger.info("جاري تحميل النافذة الرئيسية...")
            main_win = MainWindow(db)
            # ربط إشارة الخروج بعد إنشاء MainWindow
            main_win.logout_signal.connect(on_logout)
        
        main_win.setup_user_session(user) 
        main_win.show()
        login_win.hide()

    # --- عند تسجيل الخروج ---
    def on_logout():
        nonlocal main_win
        if main_win:
            main_win.close()
            main_win.init_dashboard()
        login_win.username.clear()
        login_win.password.clear()
        login_win.msg.setText("") 
        login_win.username.setFocus()
        login_win.show()

    # ربط الإشارات بالدوال
    login_win.login_success_signal = on_login_success
    
    login_win.show()
    # معالجة غلق التطبيق بدون تسجيل دخول
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
