from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.uic import loadUiType

from datetime import date
import sys
from os import path

# استيراد طبقة خدمة قاعدة البيانات الجديدة (shim keeps backward compatibility)
from services.db_services import DBService

# إخفاء تحذيرات PyQt6
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from utils import calculate_age, GlobalInputBehaviorFilter

# تقرير PDF
from services.reporting import generate_report, ReportError

# plotting for dashboard (optional)
try:
    import matplotlib as mpl
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
    mpl.rcParams['axes.unicode_minus'] = False
    for _font in ['Tahoma', 'Arial', 'Noto Naskh Arabic', 'DejaVu Sans']:
        try:
            mpl.rcParams['font.family'] = _font
            break
        except Exception:
            pass
except Exception:
    MATPLOTLIB_AVAILABLE = False
    FigureCanvas = None
    Figure = None

# Arabic shaping (optional)
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SHAPING_AVAILABLE = True
except Exception:
    ARABIC_SHAPING_AVAILABLE = False


def _prepare_arabic(text: str) -> str:
    """Reshape and reorder Arabic text for proper display in Matplotlib.

    Falls back to the original text if shaping libraries are unavailable.
    """
    if not text:
        return text
    if not ARABIC_SHAPING_AVAILABLE:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        return bidi_text
    except Exception:
        return text

# افتراض أن ملف الواجهة الرسومية (UI) موجود
FORM_CLASS, _ = loadUiType(path.join(path.dirname(__file__), "app.ui"))

class MainWindow(QMainWindow, FORM_CLASS):
    """
    النافذة الرئيسية للتطبيق (مُنفصلة كـ view). تقوم بعرض الواجهة والتعامل مع الأحداث.
    """
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.db_service = DBService()
        self.test_db_connection()
        self.init_ui()
        self.handle_buttons()
        self.handle_signals()

        # Table sizing and hides
        self.tableWidget.setColumnHidden(0, True)
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_2.setColumnHidden(0, True)
        self.tableWidget_2.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.guardians_tableWidget.setColumnHidden(0, True)
        self.guardians_tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_all_orphans.setColumnHidden(0, True)
        self.tableWidget_all_orphans.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_orphans_over_18.setColumnHidden(0, True)
        self.tableWidget_orphans_over_18.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_4.setColumnHidden(0, True)

        self.current_deceased_id = None

        try:
            self.init_dashboard()
        except Exception as e:
            print(f"Failed to initialize dashboard charts: {e}")

    # --- (All methods are kept identical to the original MainWindow implementation) ---

    def init_ui(self):
        self.setWindowTitle("نظام إدارة الأيتام")
        self.tabWidget.tabBar().setVisible(False)
        default_date = QDate(date.today().year - 20, 1, 1)
        self.dateEdit.setDate(default_date)
        self.dateEdit_4.setDate(QDate.currentDate())
        self.pushButton_guardian_update.setEnabled(False)
        self.tabWidget_4.setTabEnabled(1, False)
        try:
            self.export_report.setEnabled(False)
            self.export_report_2.setEnabled(False)
            self.export_report_3.setEnabled(False)
        except Exception:
            pass
        self.tabWidget_3.setTabEnabled(1, False)

    def init_dashboard(self):
        """Initialize dashboard chart canvases and draw initial charts."""
        if not MATPLOTLIB_AVAILABLE:
            # show helpful message in the two placeholder widgets
            for widget in (self.chartWidget, self.chartWidget_2):
                try:
                    existing_layout = widget.layout()
                    if existing_layout:
                        # clear existing layout widgets
                        for i in reversed(range(existing_layout.count())):
                            w = existing_layout.itemAt(i).widget()
                            if w:
                                w.setParent(None)
                except Exception:
                    pass

                layout = QVBoxLayout(widget)
                layout.setContentsMargins(0, 0, 0, 0)
                label = QLabel("مكتبة matplotlib غير مثبّتة. لتفعيل المخططات، ثبّتها عبر: pip install matplotlib")
                label.setWordWrap(True)
                layout.addWidget(label)
            return

        # chart 1: orphans over time
        self.figure_chart = Figure(figsize=(5, 3))
        self.canvas_chart = FigureCanvas(self.figure_chart)
        layout1 = QVBoxLayout(self.chartWidget)
        layout1.setContentsMargins(0, 0, 0, 0)
        layout1.addWidget(self.canvas_chart)
        self.ax_chart = self.figure_chart.add_subplot(111)

        # chart 2: age distribution
        self.figure_chart2 = Figure(figsize=(5, 3))
        self.canvas_chart2 = FigureCanvas(self.figure_chart2)
        layout2 = QVBoxLayout(self.chartWidget_2)
        layout2.setContentsMargins(0, 0, 0, 0)
        layout2.addWidget(self.canvas_chart2)
        self.ax_chart2 = self.figure_chart2.add_subplot(111)

        # initial draw
        self.update_dashboard_charts()

    def update_dashboard_charts(self, months: int = 12):
        """Fetch data and redraw both dashboard charts."""
        try:
            monthly = self.db_service.get_orphans_count_by_month(months)
            labels = [m for m, _ in monthly]
            counts = [c for _, c in monthly]

            self.ax_chart.clear()
            if any(counts):
                self.ax_chart.plot(labels, counts, marker='o')
                self.ax_chart.set_title(_prepare_arabic("عدد الأيتام على مر الشهور"))
                self.ax_chart.set_xlabel(_prepare_arabic("شهر"))
                self.ax_chart.set_ylabel(_prepare_arabic("عدد الأيتام"))
                self.ax_chart.tick_params(axis='x', rotation=45)
            else:
                self.ax_chart.text(0.5, 0.5, _prepare_arabic("لا توجد بيانات"), ha='center', va='center')
            try:
                self.figure_chart.tight_layout()
            except Exception:
                pass
            if not ARABIC_SHAPING_AVAILABLE:
                self.ax_chart.text(0.01, 0.01, "Install arabic-reshaper and python-bidi for proper Arabic shaping", transform=self.ax_chart.transAxes, fontsize=8, color='gray', ha='left', va='bottom')
            self.canvas_chart.draw()

            dist = self.db_service.get_age_distribution()
            labels2 = [d for d, _ in dist]
            counts2 = [c for _, c in dist]

            self.ax_chart2.clear()
            if sum(counts2) > 0:
                self.ax_chart2.bar(labels2, counts2, color='C1')
                self.ax_chart2.set_title(_prepare_arabic("توزيع أعمار الأيتام"))
                self.ax_chart2.set_ylabel(_prepare_arabic("عدد الأيتام"))
            else:
                self.ax_chart2.text(0.5, 0.5, _prepare_arabic("لا توجد بيانات"), ha='center', va='center')
            try:
                self.figure_chart2.tight_layout()
            except Exception:
                pass
            if not ARABIC_SHAPING_AVAILABLE:
                self.ax_chart2.text(0.01, 0.01, "Install arabic-reshaper and python-bidi for proper Arabic shaping", transform=self.ax_chart2.transAxes, fontsize=8, color='gray', ha='left', va='bottom')
            self.canvas_chart2.draw()

            # update summary LCDs
            try:
                self.update_summary_lcds()
            except Exception as e:
                print(f"Warning: failed to update summary LCDs: {e}")

        except Exception as e:
            print(f"Error updating dashboard charts: {e}")

    def update_summary_lcds(self):
        """Fetch summary counts and display them in the LCD widgets."""
        try:
            summary = self.db_service.get_summary_counts()
            # Orphans total
            try:
                self.lcdNumber.display(int(summary.get("orphans", 0)))
            except Exception:
                pass
            # Orphans >=18
            try:
                self.lcdNumber_2.display(int(summary.get("orphans_over_18", 0)))
            except Exception:
                pass
            # Guardians
            try:
                self.lcdNumber_3.display(int(summary.get("guardians", 0)))
            except Exception:
                pass
            # Deceased
            try:
                self.lcdNumber_4.display(int(summary.get("deceased", 0)))
            except Exception:
                pass
        except Exception as e:
            print(f"Error updating summary LCDs: {e}")

    def handle_buttons(self):
        """ربط الأزرار بالدوال الخاصة بها."""
        # Deceaseds Buttons
        self.pushButton.clicked.connect(self.add_deceased)
        self.pushButton_2.clicked.connect(self.update_deceased)
        self.pushButton_3.clicked.connect(self.delete_deceased)

        # Search Button (بحث برقم الهوية)
        self.pushButton_10.clicked.connect(self.search_by_national_id)

        # Export report buttons (will be enabled only when details are loaded)
        try:
            self.export_report.clicked.connect(self.export_deceased_report)
            self.export_report_2.clicked.connect(self.export_guardian_report)
            self.export_report_3.clicked.connect(self.export_orphan_report)
            # monthly minors report button
            self.monthly_report.clicked.connect(self.export_monthly_minors)
        except Exception:
            # In case UI doesn't include them
            pass

        # Orphans Buttons (في الواجهة الأصلية كانت فارغة، نتركها كما هي حالياً)
        # self.pushButton_4.clicked.connect(self.add_orphan)
        self.pushButton_5.clicked.connect(self.update_orphan)
        # self.pushButton_delete_orphan.clicked.connect(self.delete_orphan)
        
        # ربط أزرار إضافة وحذف صف في جدول الأيتام
        self.pushButton_add_row.clicked.connect(self.add_row_to_orphans_table)
        self.pushButton_delete_row.clicked.connect(self.delete_selected_orphan_row)
        self.pushButton_add_row_3.clicked.connect(self.add_row_to_transactions_table)
        self.pushButton_delete_row_3.clicked.connect(self.delete_selected_transaction_row)
        
        # Guardian Profile Buttons
        # self.pushButton_guardian_delete.clicked.connect(self.delete_guardian) # Corrected connection to delete_guardian
        self.pushButton_guardian_update.clicked.connect(self.update_guardian)

    def handle_signals(self):
        """ربط الإشارات (Signals) بالدوال (Slots)."""
        self.tabWidget.currentChanged.connect(self.tab_changed)
        self.tabWidget_2.currentChanged.connect(self.deceaseds_tab_changed)
        self.tabWidget_3.currentChanged.connect(self.orphan_tab_changed)
        self.tabWidget_4.currentChanged.connect(self.guardian_tab_changed)
        self.tableWidget_2.cellDoubleClicked.connect(self.deceased_row_clicked)
        self.guardians_tableWidget.cellDoubleClicked.connect(self.guardian_row_clicked)
        self.tableWidget_all_orphans.cellDoubleClicked.connect(self.orphan_row_clicked)

    # ==================================================
    # الدوال المساعدة
    # ==================================================

    def test_db_connection(self):
        """اختبار الاتصال بقاعدة البيانات."""
        if not self.db_service.test_connection():
            QMessageBox.critical(self, "خطأ", "فشل الاتصال بقاعدة البيانات. يرجى التحقق من الإعدادات.")
            # يمكن إضافة sys.exit(1) هنا لإغلاق التطبيق إذا كان الاتصال ضرورياً

    def clear_deceased_form(self):
        """تفريغ حقول إدخال المتوفى والوصي وجدول الأيتام."""
        self.lineEdit.clear()
        self.lineEdit_2.clear()
        self.dateEdit.setDate(QDate(date.today().year - 20, 1, 1))
        self.lineEdit_13.clear()
        self.lineEdit_14.clear()
        self.lineEdit_15.clear()
        self.dateEdit_4.setDate(QDate.currentDate())
        self.comboBox_4.setCurrentIndex(0)
        self.tableWidget.setRowCount(0)
        self.current_deceased_id = None
        self.pushButton.setEnabled(True) # زر الإضافة
        self.pushButton_2.setEnabled(False) # زر التعديل
        self.pushButton_3.setEnabled(False) # زر الحذف

        # تعطيل زر تصدير التقرير لأن لا يوجد متوفى محدد الآن
        try:
            self.export_report.setEnabled(False)
        except Exception:
            pass

    def clear_guardian_form(self):
        """تفريغ حقول إدخال الوصي وجدول الأيتام في شاشة ملف الوصي."""
        # Assuming the guardian profile fields are named:
        # lineEdit_guardian_name, lineEdit_guardian_nid, lineEdit_guardian_phone, dateEdit_guardian_appointment, comboBox_guardian_relationship
        # And the orphans table is named tableWidget_guardian_orphans
        
        self.lineEdit_guardian_name.clear()
        self.lineEdit_guardian_nid.clear()
        self.lineEdit_guardian_phone.clear()
        self.dateEdit_guardian_appointment.setDate(QDate.currentDate())
        self.comboBox_guardian_relationship.setCurrentIndex(0)
        self.tableWidget_guardian_orphans.setRowCount(0)
        self.current_guardian_id = None
        
        # تعطيل أزرار التعديل والمسح
        self.pushButton_guardian_update.setEnabled(False)
        # self.pushButton_guardian_delete.setEnabled(False)
        self.tabWidget_4.setTabEnabled(1, False)

        # تعطيل زر تصدير التقرير لأن لا يوجد وصي محدد الآن
        try:
            self.export_report_2.setEnabled(False)
        except Exception:
            pass

    def delete_guardian(self):
        """حذف سجل الوصي الحالي فقط."""
        if self.current_guardian_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار وصي للحذف أولاً.")
            return

        reply = QMessageBox.question(self, 'تأكيد الحذف',
            f"هل أنت متأكد من حذف الوصي رقم {self.current_guardian_id}؟\n(ملاحظة: لن يتم حذف الأيتام المرتبطين به)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db_service.delete_guardian(self.current_guardian_id)
                QMessageBox.information(self, "نجاح", "تم حذف الوصي بنجاح.")
                self.clear_guardian_form()
                self.load_guardians_list()
            except Exception as e:
                QMessageBox.critical(self, "خطأ في الحذف", f"فشل حذف الوصي:\n{str(e)}")
                print(f"Error deleting guardian: {e}")

    def guardian_row_clicked(self, row, column):
        """معالجة النقر على صف في جدول الأوصياء."""
        try:
            item = self.guardians_tableWidget.item(row, 0)
            if item:
                guardian_id = int(item.text())
                self.current_guardian_id = guardian_id
                self.load_guardian_details(guardian_id)
                
                # تفعيل أزرار التعديل والمسح
                # self.pushButton_guardian_delete.setEnabled(True)
                self.pushButton_guardian_update.setEnabled(True)
                self.tabWidget_4.setTabEnabled(1, True)

                # تفعيل زر تصدير التقرير
                try:
                    self.export_report_2.setEnabled(True)
                except Exception:
                    pass

                # الانتقال إلى تبويب ملف الوصي (نفترض أنه التبويب الفرعي رقم 1 في تبويب الأوصياء)
                self.tabWidget_4.setCurrentIndex(1) # الانتقال إلى تبويب الأوصياء
                # يجب أن يكون هناك تبويب فرعي داخل تبويب الأوصياء للانتقال إليه
                # سنفترض أن التبويب الفرعي للأوصياء اسمه self.tabWidget_guardians
                # self.tabWidget_guardians.setCurrentIndex(1) # الانتقال إلى ملف الوصي
                
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تحديد الوصي:\n{str(e)}")

    def get_deceased_form_data(self):
        """استخراج بيانات المتوفى والوصي من الواجهة مع التحقق الأولي."""
        
        # قراءة بيانات المتوفّى
        name = self.lineEdit.text().strip()
        national_id = self.lineEdit_2.text().strip()
        qdate_death = self.dateEdit.date()
        
        # قراءة بيانات الوصي
        guardian_name = self.lineEdit_13.text().strip()
        guardian_national_id = self.lineEdit_14.text().strip()
        guardian_phone = self.lineEdit_15.text().strip()
        qdate_appointment = self.dateEdit_4.date()
        guardian_relationship = self.comboBox_4.currentIndex()

        # التحقق من بيانات المتوفى
        if not name:
            raise ValueError("يرجى إدخال اسم المتوفّى")
        if not national_id.isdigit() or len(national_id) != 9:
            raise ValueError("رقم الهوية للمتوفّى غير صالح (يجب أن يكون 9 أرقام)")
        if not qdate_death.isValid():
            raise ValueError("يرجى إدخال تاريخ وفاة صحيح")
        date_of_death = date(qdate_death.year(), qdate_death.month(), qdate_death.day())
        if date_of_death > date.today():
            raise ValueError("تاريخ الوفاة لا يمكن أن يكون في المستقبل")

        # التحقق من بيانات الوصي
        if not guardian_name:
            raise ValueError("يرجى إدخال اسم الوصي الشرعي")
        if not guardian_national_id.isdigit() or len(guardian_national_id) != 9:
            raise ValueError("رقم الهوية للوصي غير صالح (يجب أن يكون 9 أرقام)")
        if not qdate_appointment.isValid():
            raise ValueError("يرجى اختيار تاريخ تعيين الوصي")
        appointment_date = date(qdate_appointment.year(), qdate_appointment.month(), qdate_appointment.day())
        if appointment_date > date.today():
            raise ValueError("تاريخ تعيين الوصي لا يمكن أن يكون في المستقبل")
        if guardian_relationship == 0:
            raise ValueError("يرجى اختيار العلاقة بين اليتيم والوصي")

        deceased_data = {
            "name": name,
            "national_id": national_id,
            "date_of_death": date_of_death
        }
        
        guardian_data = {
            "name": guardian_name,
            "national_id": guardian_national_id,
            "phone": guardian_phone,
            "relationship": guardian_relationship,
            "appointment_date": appointment_date
        }
        
        return deceased_data, guardian_data

    def get_orphan_form_data(self):
        """استخراج بيانات اليتيم من نموذج الإدخال مع التحقق."""
        name = self.lineEdit_3.text().strip()
        national_id = self.lineEdit_4.text().strip()
        qdate_dob = self.dateEdit_2.date()
        gender = self.comboBox.currentIndex()

        # التحقق من بيانات اليتيم
        if not name:
            raise ValueError("يرجى إدخال اسم اليتيم")
        if not national_id.isdigit() or len(national_id) != 9:
            raise ValueError("رقم الهوية لليتيم غير صالح (يجب أن يكون 9 أرقام)")
        if not qdate_dob.isValid():
            raise ValueError("يرجى إدخال تاريخ ميلاد صحيح")
        date_of_birth = date(qdate_dob.year(), qdate_dob.month(), qdate_dob.day())
        if date_of_birth > date.today():
            raise ValueError("تاريخ الميلاد لا يمكن أن يكون في المستقبل")

        orphan_data = {
            "name": name,
            "national_id": national_id,
            "date_of_birth": date_of_birth,
            "gender": gender
        }

        return orphan_data

    def get_transactions_table_data(self):
        table = self.tableWidget_4
        transactions_data = []

        for row in range(table.rowCount()):
            transaction_id_item = table.item(row, 0)
            transaction_id = int(transaction_id_item.text()) if transaction_id_item and transaction_id_item.text().isdigit() else None

            currency_widget = table.cellWidget(row, 1)
            type_widget = table.cellWidget(row, 2)

            # Fallback to text cell if widget was not created
            currency_text = None
            if currency_widget and isinstance(currency_widget, QComboBox):
                currency_text = currency_widget.currentText()
            else:
                currency_item = table.item(row, 1)
                currency_text = currency_item.text().strip() if currency_item else ""

            type_text = None
            if type_widget and isinstance(type_widget, QComboBox):
                type_text = type_widget.currentText()
            else:
                type_item = table.item(row, 2)
                type_text = type_item.text().strip() if type_item else ""

            if not currency_text or currency_text == "اختر":
                raise ValueError(f"يرجى اختيار العملة في الصف {row+1}")
            if not type_text or type_text == "اختر":
                raise ValueError(f"يرجى اختيار نوع العملية في الصف {row+1}")

            amount_item = table.item(row, 3)
            date_item = table.item(row, 4)
            note_item = table.item(row, 5)

            if not amount_item or not amount_item.text().strip():
                raise ValueError(f"يرجى إدخال المبلغ في الصف {row+1}")

            # Parse date (expecting yyyy-mm-dd format)

            date_widget = table.cellWidget(row, 4)
            tx_date = date_widget.date().toPyDate() if date_widget else None

            transaction_data = {
                "id": transaction_id,
                "currency": currency_text,
                "type": type_text,
                "amount": float(amount_item.text()),
                "date": tx_date,
                "note": note_item.text() if note_item else None,
            }

            transactions_data.append(transaction_data)

        if not transactions_data:
            raise ValueError("يجب إضافة عملية واحدة على الأقل")

        return transactions_data


    def get_orphans_table_data(self, table_widget):
        """استخراج بيانات الأيتام من جدول QTableWidget مع التحقق."""
        orphans_data = []
        table = table_widget
        for row in range(table.rowCount()):
            try:
                # افتراض أن الأعمدة هي: 0: ID (مخفي), 1: الاسم, 2: رقم الهوية, 3: تاريخ الميلاد (QDateEdit), 4: الجنس (QComboBox)
                
                # قراءة ID اليتيم (إذا كان موجوداً)
                orphan_id_item = table.item(row, 0)
                orphan_id = int(orphan_id_item.text()) if orphan_id_item and orphan_id_item.text().isdigit() else None
                
                # قراءة البيانات من QTableWidgetItem
                orphan_name_item = table.item(row, 1)
                orphan_nid_item = table.item(row, 2)
                
                orphan_name = orphan_name_item.text().strip() if orphan_name_item else ""
                orphan_nid = orphan_nid_item.text().strip() if orphan_nid_item else ""
                
                # قراءة البيانات من QWidget
                dob_widget = table.cellWidget(row, 3)
                gender_widget = table.cellWidget(row, 4)
                
                dob = dob_widget.date().toPyDate() if dob_widget else None
                gender = gender_widget.currentIndex() if gender_widget else 0
                
                # التحقق من البيانات
                if not orphan_name:
                    raise ValueError(f"يرجى إدخال اسم اليتيم في الصف {row+1}")
                if not orphan_nid.isdigit() or len(orphan_nid) != 9:
                    raise ValueError(f"رقم الهوية لليتيم في الصف {row+1} غير صالح (يجب أن يكون 9 أرقام)")
                if not dob:
                    raise ValueError(f"يرجى إدخال تاريخ ميلاد اليتيم في الصف {row+1}")
                if gender == 0:
                    raise ValueError(f"يرجى اختيار جنس اليتيم في الصف {row+1}")

                orphan_data = {
                    "name": orphan_name,
                    "national_id": orphan_nid,
                    "date_of_birth": dob,
                    "gender": gender,
                }
                if orphan_id is not None:
                    orphan_data["id"] = orphan_id
                    
                orphans_data.append(orphan_data)
            except ValueError as e:
                raise e # إعادة إطلاق خطأ التحقق
            except Exception:
                raise ValueError(f"خطأ في قراءة بيانات الصف {row+1}. تأكد من ملء جميع الحقول.")

        if not orphans_data:
            raise ValueError("يجب إضافة يتيم واحد على الأقل.")
            
        return orphans_data

    # ==================================================
    # معالجة إشارات الواجهة
    # ==================================================

    def tab_changed(self, index):
        """معالجة تغيير التبويب الرئيسي."""
        tab_name = self.tabWidget.tabText(index)
        print(f"Current Tab Index: {index}, Name: {tab_name}")
        
        # نفترض أن تبويب "المتوفين" هو الفهرس 1 (كما كان في الكود الأصلي)
        if index == 1: 
            self.load_deceaseds()
        # تم التأكيد على أن الفهرس الصحيح لـ "قائمة الأوصياء" هو 2
        elif index == 2: 
            self.load_guardians_list()
        # تم التأكيد على أن الفهرس الصحيح لـ "قائمة الأيتام" هو 2
        elif index == 3: 
            self.load_orphans()
        # تبويب الأيتام الأكبر من 18 سنة
        elif index == 4:
            self.load_orphans_older_than_18()

    def deceaseds_tab_changed(self, index):
        """معالجة تغيير التبويب الفرعي للمتوفين (إضافة/عرض)."""
        print("Current nested Tab Index:", index)
        if index == 0: # تبويب الإضافة
            self.clear_deceased_form()
            self.pushButton.setEnabled(True) # تفعيل زر الإضافة
            self.pushButton_2.setEnabled(False) # تعطيل زر التعديل
            self.pushButton_3.setEnabled(False) # تعطيل زر الحذف
            self.export_report.setEnabled(False) # تعطيل زر التصدير
    
    def deceased_row_clicked(self, row, column):
        """معالجة الضغط على صف في جدول المتوفين."""
        try:
            item = self.tableWidget_2.item(row, 0)
            if item:
                deceased_id = int(item.text())
                self.current_deceased_id = deceased_id
                self.load_deceased_details(deceased_id)
                
                # تفعيل أزرار التعديل والحذف
                self.pushButton.setEnabled(False)
                self.pushButton_2.setEnabled(True)
                self.pushButton_3.setEnabled(True)
                
                self.tabWidget_2.setCurrentIndex(1)

                # تفعيل زر تصدير التقرير كتحقق إضافي
                try:
                    self.export_report.setEnabled(True)
                except Exception:
                    pass
            
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تحديد المتوفى:\n{str(e)}")

    def search_by_national_id(self):
        """Search UI handler: reads `lineEdit_10`, queries DB, and navigates to results."""
        nid = self.lineEdit_10.text().strip()
        if not nid:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال رقم الهوية للبحث.")
            return
        if not nid.isdigit() or len(nid) != 9:
            QMessageBox.warning(self, "تنبيه", "رقم الهوية غير صالح (يجب أن يكون 9 أرقام).")
            return

        try:
            res = self.db_service.search_by_national_id(nid)
            found = []
            if res.get("orphan"):
                found.append(("يتيم", res["orphan"]))
            if res.get("guardian"):
                found.append(("وصي", res["guardian"]))
            if res.get("deceased"):
                found.append(("متوفّى", res["deceased"]))

            if not found:
                QMessageBox.information(self, "نتيجة البحث", "لم يتم العثور على سجلات برقم الهوية هذا.")
                return

            # If more than one match, let user choose which to open
            if len(found) == 1:
                kind, obj = found[0]
            else:
                options = [f"{k} (ID: {getattr(o, 'id', '?')})" for k, o in found]
                item, ok = QInputDialog.getItem(self, "اختيار النتيجة", "تم العثور على عدة سجلات، اختر ما تريد عرضه:", options, 0, False)
                if not ok:
                    return
                idx = options.index(item)
                kind, obj = found[idx]

            # Navigate to the appropriate tab and load details
            if kind == "يتيم":
                self.load_orphan_details(obj.id)
                self.tabWidget.setCurrentIndex(3)
                self.tabWidget_3.setCurrentIndex(1)
                self.tabWidget_3.setTabEnabled(1, True)
                self.listWidget.setCurrentRow(3)  # Select item in the list
                # تأكد أن زر التصدير مفعل
                try:
                    self.export_report_3.setEnabled(True)
                except Exception:
                    pass
            elif kind == "وصي":
                self.load_guardian_details(obj.id)
                self.tabWidget.setCurrentIndex(2)
                self.tabWidget_4.setCurrentIndex(1)
                self.tabWidget_4.setTabEnabled(1, True)
                self.listWidget.setCurrentRow(2)  # Select item in the list
                # تأكد أن زر التصدير مفعل
                try:
                    self.export_report_2.setEnabled(True)
                except Exception:
                    pass
            elif kind == "متوفّى":
                # Ensure deceaseds table is loaded so we can select the row
                try:
                    self.load_deceaseds()
                except Exception:
                    pass

                # Try to find and select the row in the table
                try:
                    found_row = None
                    for r in range(self.tableWidget_2.rowCount()):
                        item = self.tableWidget_2.item(r, 0)
                        if item and item.text() == str(obj.id):
                            found_row = r
                            break
                    if found_row is not None:
                        self.tableWidget_2.selectRow(found_row)
                        self.current_deceased_id = obj.id
                except Exception:
                    pass

                # Load details and switch to the deceased tab/view
                self.load_deceased_details(obj.id)
                self.tabWidget.setCurrentIndex(1)
                self.tabWidget_2.setCurrentIndex(1)
                self.tabWidget_2.setTabEnabled(1, True)
                self.listWidget.setCurrentRow(1)  # Select item in the list
                # تفعيل أزرار التعديل والحذف
                self.pushButton.setEnabled(False)
                self.pushButton_2.setEnabled(True)
                self.pushButton_3.setEnabled(True)

                # تفعيل زر التصدير (في حال جئنا من البحث)
                try:
                    self.export_report.setEnabled(True)
                except Exception:
                    pass

        except Exception as e:
            QMessageBox.critical(self, "خطأ في البحث", str(e))
    
    def orphan_row_clicked(self, row, column):
        """معالجة الضغط على صف في جدول الأيتام."""
        try:
            item = self.tableWidget_all_orphans.item(row, 0)
            if item:
                orphan_id = int(item.text())
                self.current_orphan_id = orphan_id
                self.load_orphan_details(orphan_id)
                
                # تفعيل أزرار التعديل والحذف
                # self.pushButton_4.setEnabled(False)
                # self.pushButton_5.setEnabled(True)
                # self.pushButton_delete_orphan.setEnabled(True)
                
                self.tabWidget_3.setCurrentIndex(1)
                self.tabWidget_3.setTabEnabled(1, True)
            
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تحديد اليتيم:\n{str(e)}")

    # ==================================================
    # Export report handlers
    # ==================================================
    def export_orphan_report(self):
        if not hasattr(self, "current_orphan_id") or self.current_orphan_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار يتيم لتصدير تقريره أولاً.")
            return

        default_name = f"report_orphan_{self.current_orphan_id}_{date.today().strftime('%Y%m%d')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير", default_name, "PDF Files (*.pdf)")
        if not path:
            return
        try:
            generate_report("orphan", self.current_orphan_id, path)
            QMessageBox.information(self, "تم", f"تم حفظ التقرير في: {path}")
        except ReportError as re:
            QMessageBox.critical(self, "خطأ في التصدير", str(re))
        except Exception as e:
            print(f"Error exporting orphan report: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تصدير التقرير:\n{str(e)}")

    def export_deceased_report(self):
        if not hasattr(self, "current_deceased_id") or self.current_deceased_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار متوفّى لتصدير ملفه أولاً.")
            return

        default_name = f"report_deceased_{self.current_deceased_id}_{date.today().strftime('%Y%m%d')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير", default_name, "PDF Files (*.pdf)")
        if not path:
            return
        try:
            generate_report("deceased", self.current_deceased_id, path)
            QMessageBox.information(self, "تم", f"تم حفظ التقرير في: {path}")
        except ReportError as re:
            QMessageBox.critical(self, "خطأ في التصدير", str(re))
        except Exception as e:
            print(f"Error exporting deceased report: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تصدير التقرير:\n{str(e)}")

    def export_guardian_report(self):
        if not hasattr(self, "current_guardian_id") or self.current_guardian_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار وصي لتصدير ملفه أولاً.")
            return

        default_name = f"report_guardian_{self.current_guardian_id}_{date.today().strftime('%Y%m%d')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير", default_name, "PDF Files (*.pdf)")
        if not path:
            return
        try:
            generate_report("guardian", self.current_guardian_id, path)
            QMessageBox.information(self, "تم", f"تم حفظ التقرير في: {path}")
        except ReportError as re:
            QMessageBox.critical(self, "خطأ في التصدير", str(re))
        except Exception as e:
            print(f"Error exporting guardian report: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تصدير التقرير:\n{str(e)}")
    
    def export_monthly_minors(self):
        """Export monthly minors report as CSV or PDF for last N months."""
        try:
            months, ok = QInputDialog.getInt(self, "عدد الأشهر", "عدد الأشهر:", 12, 1, 120)
            if not ok:
                return

            fmt, ok2 = QInputDialog.getItem(self, "نوع الملف", "اختر نوع الملف:", ["PDF", "CSV"], 0, False)
            if not ok2:
                return

            data = self.db_service.get_minors_count_by_month(months)
            if not data:
                QMessageBox.information(self, "لا توجد بيانات", "لا توجد بيانات لتصديرها.")
                return

            if fmt == "CSV":
                default_name = f"monthly_minors_{date.today().strftime('%Y%m%d')}.csv"
                path, _ = QFileDialog.getSaveFileName(self, "حفظ تقرير شهري", default_name, "CSV Files (*.csv)")
                if not path:
                    return
                import csv
                with open(path, "w", encoding="utf-8", newline='') as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["month", "count"])
                    for label, cnt in data:
                        writer.writerow([label, cnt])
                QMessageBox.information(self, "نجاح", f"تم حفظ التقرير في {path}")
                return

            # PDF path
            default_name = f"monthly_minors_{date.today().strftime('%Y%m%d')}.pdf"
            path, _ = QFileDialog.getSaveFileName(self, "حفظ تقرير شهري (PDF)", default_name, "PDF Files (*.pdf)")
            if not path:
                return
            # We call generate_report with entity_type 'monthly_minors' and entity_id = months
            try:
                generate_report("monthly_minors", months, path)
                QMessageBox.information(self, "تم", f"تم حفظ التقرير في: {path}")
            except ReportError as re:
                QMessageBox.critical(self, "خطأ في التصدير", str(re))
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تصدير التقرير:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تصدير التقرير:\n{e}")
    
    def guardian_tab_changed(self, index):
        """معالجة تغيير التبويب الفرعي للأوصياء (إضافة/عرض)."""
        print("Current nested Tab Index:", index)
        if index == 0:
            self.clear_guardian_form()
            self.pushButton_guardian_update.setEnabled(False)
            # self.pushButton_guardian_delete.setEnabled(False)
    
    def orphan_tab_changed(self, index):
        """معالجة تغيير التبويب الفرعي للأيتام (إضافة/عرض)."""
        print("Current nested Tab Index:", index)
        if index == 0:
            self.tabWidget_3.setTabEnabled(1, False)
            # self.clear_orphan_form()
            # self.pushButton_4.setEnabled(True)
            # self.pushButton_5.setEnabled(False)
            # self.pushButton_delete_orphan.setEnabled(False)
            try:
                self.export_report_3.setEnabled(False)
            except Exception:
                pass

    # ==================================================
    # دوال CRUD للمتوفين
    # ==================================================

    def load_deceaseds(self):
        """تحميل بيانات المتوفين في جدول العرض."""
        self.pushButton_2.setEnabled(False)
        self.pushButton_3.setEnabled(False)
        try:
            data = self.db_service.load_deceaseds_with_orphan_count()

            table = self.tableWidget_2
            table.setRowCount(len(data))

            for row_idx, (d, orphans_count) in enumerate(data):
                table.setItem(row_idx, 0, QTableWidgetItem(str(d.id)))
                table.setItem(row_idx, 1, QTableWidgetItem(d.name))
                table.setItem(row_idx, 2, QTableWidgetItem(d.national_id or ""))
                table.setItem(row_idx, 3, QTableWidgetItem(
                    d.date_of_death.strftime("%d/%m/%Y") if d.date_of_death else ""
                ))
                table.setItem(row_idx, 4, QTableWidgetItem(str(orphans_count)))

        except Exception as e:
            print(f"Error loading deceaseds: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات المتوفين:\n{str(e)}")

    def load_guardians_list(self):
        """تحميل قائمة الأوصياء في جدول العرض."""
        try:
            guardians_data = self.db_service.load_guardians_with_orphan_count()
            
            table = self.guardians_tableWidget
            table.setRowCount(0) # Clear existing rows
            
            for row_num, (guardian, orphan_count) in enumerate(guardians_data):
                table.insertRow(row_num)
                
                # ID (Hidden)
                table.setItem(row_num, 0, QTableWidgetItem(str(guardian.id)))
                # Name
                table.setItem(row_num, 1, QTableWidgetItem(guardian.name))
                # National ID
                table.setItem(row_num, 2, QTableWidgetItem(guardian.national_id))
                # Phone Number
                table.setItem(row_num, 3, QTableWidgetItem(guardian.phone or ""))
                # Orphan Count
                table.setItem(row_num, 4, QTableWidgetItem(str(orphan_count)))
                
        except Exception as e:
            QMessageBox.critical(self, "خطأ في تحميل الأوصياء", f"حدث خطأ أثناء تحميل قائمة الأوصياء:\n{e}")
            print(f"Error loading guardians list: {e}")

    def load_deceased_details(self, deceased_id):
        """تحميل تفاصيل متوفى محدد في نموذج الإدخال."""
        try:
            deceased, orphans, guardian = self.db_service.get_deceased_details(deceased_id)
            
            if not deceased:
                QMessageBox.warning(self, "تنبيه", "لم يتم العثور على بيانات المتوفى.")
                return

            # ملء بيانات المتوفى
            self.lineEdit.setText(deceased.name)
            self.lineEdit_2.setText(deceased.national_id)
            if deceased.date_of_death:
                self.dateEdit.setDate(QDate(
                    deceased.date_of_death.year,
                    deceased.date_of_death.month,
                    deceased.date_of_death.day
                ))

            # ملء بيانات الوصي
            if guardian:
                self.lineEdit_13.setText(guardian.name)
                self.lineEdit_14.setText(guardian.national_id)
                self.lineEdit_15.setText(guardian.phone)
                if guardian.appointment_date:
                    self.dateEdit_4.setDate(QDate(
                        guardian.appointment_date.year,
                        guardian.appointment_date.month,
                        guardian.appointment_date.day
                    ))
                self.comboBox_4.setCurrentIndex(guardian.relationship)
            else:
                # مسح حقول الوصي إذا لم يوجد
                self.lineEdit_13.clear()
                self.lineEdit_14.clear()
                self.lineEdit_15.clear()
                self.dateEdit_4.setDate(QDate.currentDate())
                self.comboBox_4.setCurrentIndex(0)

            # ملء جدول الأيتام
            table = self.tableWidget
            table.setRowCount(len(orphans))
            
            for row_idx, orphan in enumerate(orphans):
                # ID (مخفي)
                table.setItem(row_idx, 0, QTableWidgetItem(str(orphan.id)))
                # الاسم
                table.setItem(row_idx, 1, QTableWidgetItem(orphan.name or ""))
                # رقم الهوية
                table.setItem(row_idx, 2, QTableWidgetItem(orphan.national_id or ""))

                # تاريخ الميلاد (QDateEdit)
                date_edit = QDateEdit()
                date_edit.setCalendarPopup(True)
                date_edit.setDisplayFormat("yyyy/MM/dd")
                if orphan.date_of_birth:
                    date_edit.setDate(QDate(
                        orphan.date_of_birth.year,
                        orphan.date_of_birth.month,
                        orphan.date_of_birth.day
                    ))
                else:
                    date_edit.setDate(QDate(2000, 1, 1))
                table.setCellWidget(row_idx, 3, date_edit)

                # الجنس (QComboBox)
                gender_combo = QComboBox()
                gender_combo.addItems(["اختر", "ذكر", "أنثى"])
                gender_combo.setCurrentIndex(orphan.gender) # نفترض أن 1=ذكر، 2=أنثى
                table.setCellWidget(row_idx, 4, gender_combo)

            # الانتقال إلى تبويب العرض (تفاصيل المتوفّى)
            self.tabWidget_2.setCurrentIndex(1)

            # تم تحميل بيانات المتوفى -> تفعيل زر تصدير التقرير
            try:
                self.export_report.setEnabled(True)
            except Exception:
                pass

        except Exception as e:
            print(f"Error loading deceased details: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل عرض بيانات المتوفّي:\n{str(e)}")

    def load_orphan_details(self, orphan_id):
        try:
            orphan = self.db_service.get_orphan_details(orphan_id)
            orphan_transactions = self.db_service.get_orphan_transactions(orphan_id)
            orphan_balances = self.db_service.get_orphan_balances(orphan_id)
            print(f"Orphan Balances: {orphan_balances}")
            
            self.lineEdit_3.setText(orphan.name)
            self.lineEdit_4.setText(orphan.national_id)
            self.comboBox.setCurrentIndex(orphan.gender)
            
            # تحويل تاريخ الميلاد من datetime.date إلى QDate
            if orphan.date_of_birth:
                self.dateEdit_2.setDate(QDate(orphan.date_of_birth.year,
                                            orphan.date_of_birth.month,
                                            orphan.date_of_birth.day))
            
            # ======================
            # عرض الوصي الشرعي
            # ======================
            primary_guardian = next(
                (link.guardian for link in orphan.guardian_links if link.is_primary),
                None
            )

            self.lineEdit_8.setText(primary_guardian.name if primary_guardian else "")
            self.lineEdit_9.setText(primary_guardian.national_id if primary_guardian else "")
            self.comboBox_3.setCurrentIndex(
                primary_guardian.relationship if primary_guardian else 0
            )
            if primary_guardian and primary_guardian.appointment_date:
                self.dateEdit_3.setDate(QDate(
                    primary_guardian.appointment_date.year,
                    primary_guardian.appointment_date.month,
                    primary_guardian.appointment_date.day
                ))
            else:
                self.dateEdit_3.setDate(QDate.currentDate())
            
            
            table = self.tableWidget_3
            table.setRowCount(len(orphan_balances))
            for row_idx, item in enumerate(orphan_balances):
                table.setItem(row_idx, 0, QTableWidgetItem(str(item.currency.name)))
                table.setItem(row_idx, 1, QTableWidgetItem(str(item.balance)))

            table = self.tableWidget_4
            table.setRowCount(len(orphan_transactions))

            # Prepare currency list for combos
            currencies = self.db_service.get_currency_names()
            currency_names = [c.name for c in currencies]

            for row_idx, transaction in enumerate(orphan_transactions):
                table.setItem(row_idx, 0, QTableWidgetItem(str(transaction["id"])))

                # Currency combo
                combo_currency = QComboBox()
                combo_currency.addItems(['اختر'] + currency_names)
                idx = combo_currency.findText(transaction["currency"]) if transaction["currency"] else -1
                combo_currency.setCurrentIndex(idx if idx != -1 else 0)
                table.setCellWidget(row_idx, 1, combo_currency)
                # Transaction type combo
                combo_type = QComboBox()
                combo_type.addItems(["اختر", "إيداع", "سحب"])
                idx2 = combo_type.findText(transaction["type"]) if transaction["type"] else -1
                combo_type.setCurrentIndex(idx2 if idx2 != -1 else 0)
                table.setCellWidget(row_idx, 2, combo_type)
                # Amount
                table.setItem(row_idx, 3, QTableWidgetItem(str(transaction["amount"])))
                # Date (QDateEdit)
                date_edit = QDateEdit()
                date_edit.setCalendarPopup(True)
                date_edit.setDisplayFormat("dd/MM/yyyy")
                if transaction["date"]:
                    date_edit.setDate(QDate(
                        transaction["date"].year,
                        transaction["date"].month,
                        transaction["date"].day
                    ))
                else:
                    date_edit.setDate(QDate.currentDate())
                table.setCellWidget(row_idx, 4, date_edit)
                # Note
                table.setItem(row_idx, 5, QTableWidgetItem(transaction["note"]))

            # تم تحميل بيانات اليتيم -> تفعيل زر تصدير التقرير
            try:
                self.export_report_3.setEnabled(True)
            except Exception:
                pass
            
        except Exception as e:
            print(f"Error loading orphan details: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل عرض بيانات اليتيم:\n{str(e)}")

    def load_orphans(self):
        """تحميل جميع الأيتام في جدول العرض."""
        try:
            orphans = self.db_service.load_all_orphans()

            table = self.tableWidget_all_orphans
            table.setRowCount(len(orphans))

            for row_idx, orphan in enumerate(orphans):
                table.setItem(row_idx, 0, QTableWidgetItem(str(orphan.id)))
                table.setItem(row_idx, 1, QTableWidgetItem(orphan.name))
                table.setItem(row_idx, 2, QTableWidgetItem(orphan.national_id or ""))
                table.setItem(row_idx, 3, QTableWidgetItem(
                    orphan.date_of_birth.strftime("%d/%m/%Y")
                    if orphan.date_of_birth else ""
                ))
                gender_str = "ذكر" if orphan.gender == 1 else "أنثى"
                table.setItem(row_idx, 4, QTableWidgetItem(gender_str))
                
                # العمر
                age = calculate_age(orphan.date_of_birth) if orphan.date_of_birth else "-"
                table.setItem(row_idx, 5, QTableWidgetItem(str(age)))
                # =========================
                # 👈 الوصي الشرعي
                # =========================
                primary_guardian = next(
                    (link.guardian for link in orphan.guardian_links if link.is_primary),
                    None
                )

                guardian_name = primary_guardian.name if primary_guardian else "-"
                table.setItem(row_idx, 6, QTableWidgetItem(guardian_name))

        except Exception as e:
            print(f"Error loading all orphans: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات الأيتام:\n{str(e)}")
    
    def load_orphans_older_than_18(self):
        """تحميل الأيتام الذين تجاوزوا عمر 18 سنة في جدول العرض."""
        try:
            orphans = self.db_service.load_orphans_older_than_or_equal_18()

            table = self.tableWidget_orphans_over_18
            table.setRowCount(len(orphans))

            for row_idx, orphan in enumerate(orphans):
                table.setItem(row_idx, 0, QTableWidgetItem(str(orphan.id)))
                table.setItem(row_idx, 1, QTableWidgetItem(orphan.name))
                table.setItem(row_idx, 2, QTableWidgetItem(orphan.national_id or ""))
                table.setItem(row_idx, 3, QTableWidgetItem(
                    orphan.date_of_birth.strftime("%d/%m/%Y") if orphan.date_of_birth else ""
                ))
                gender_str = "ذكر" if orphan.gender == 1 else "أنثى"
                table.setItem(row_idx, 4, QTableWidgetItem(gender_str))
                # حساب العمر
                age = calculate_age(orphan.date_of_birth) if orphan.date_of_birth else "-"
                table.setItem(row_idx, 5, QTableWidgetItem(str(age)))

        except Exception as e:
            print(f"Error loading orphans older than 18: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات الأيتام الأكبر من 18 سنة:\n{str(e)}")

    def add_deceased(self):
        """إضافة متوفى جديد، ووصي، والأيتام المرتبطين بهم."""
        try:
            deceased_data, guardian_data = self.get_deceased_form_data()
            orphans_data = self.get_orphans_table_data(self.tableWidget)
            
            self.db_service.add_deceased_and_orphans(deceased_data, guardian_data, orphans_data)
            
            self.clear_deceased_form()
            self.load_deceaseds()
            try:
                self.update_dashboard_charts()
            except Exception as e:
                print(f"Warning: failed to update dashboard charts after add_deceased: {e}")
            QMessageBox.information(self, "نجاح", "تمت إضافة المتوفّى والأيتام وربط الوصي بنجاح")

        except ValueError as ve:
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            print(f"Error adding deceased: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل عملية الإضافة:\n{str(e)}")

    def update_deceased(self):
        """تعديل بيانات المتوفى والوصي والأيتام."""
        if self.current_deceased_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد متوفى للتعديل أولاً.")
            return

        try:
            deceased_data, guardian_data = self.get_deceased_form_data()
            orphans_data = self.get_orphans_table_data(self.tableWidget)
            
            # 1. استدعاء دالة التحديث في طبقة الخدمة
            self.db_service.update_deceased_and_orphans(
                self.current_deceased_id, 
                deceased_data, 
                guardian_data, 
                orphans_data
            )
            
            # 2. عرض رسالة نجاح وتحديث العرض
            self.clear_deceased_form()
            self.load_deceaseds()
            try:
                self.update_dashboard_charts()
            except Exception as e:
                print(f"Warning: failed to update dashboard charts after update_deceased: {e}")
            QMessageBox.information(self, "نجاح", "تم تحديث بيانات المتوفّى والأيتام والوصي بنجاح")
            self.tabWidget_2.setCurrentIndex(0)

        except ValueError as ve:
            QMessageBox.warning(self, "تنبيه", str(ve))
        except Exception as e:
            print(f"Error updating deceased: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل عملية التعديل:\n{str(e)}")

    def get_guardian_form_data(self):
        """استخراج بيانات الوصي من الواجهة مع التحقق الأولي."""
        
        # قراءة بيانات الوصي
        guardian_name = self.lineEdit_guardian_name.text().strip()
        guardian_national_id = self.lineEdit_guardian_nid.text().strip()
        guardian_phone = self.lineEdit_guardian_phone.text().strip()
        qdate_appointment = self.dateEdit_guardian_appointment.date()
        guardian_relationship = self.comboBox_guardian_relationship.currentIndex()

        # التحقق من بيانات الوصي
        if not guardian_name:
            raise ValueError("يرجى إدخال اسم الوصي الشرعي")
        if not guardian_national_id.isdigit() or len(guardian_national_id) != 9:
            raise ValueError("رقم الهوية للوصي غير صالح (يجب أن يكون 9 أرقام)")
        if not qdate_appointment.isValid():
            raise ValueError("يرجى اختيار تاريخ تعيين الوصي")
        appointment_date = date(qdate_appointment.year(), qdate_appointment.month(), qdate_appointment.day())
        if appointment_date > date.today():
            raise ValueError("تاريخ تعيين الوصي لا يمكن أن يكون في المستقبل")
        if guardian_relationship == 0:
            raise ValueError("يرجى اختيار العلاقة بين اليتيم والوصي")

        guardian_data = {
            "name": guardian_name,
            "national_id": guardian_national_id,
            "phone": guardian_phone,
            "relationship": guardian_relationship,
            "appointment_date": appointment_date
        }
        
        return guardian_data

    def load_guardian_details(self, guardian_id):
        """تحميل تفاصيل وصي محدد في نموذج الإدخال."""
        try:
            guardian, orphans = self.db_service.get_guardian_details(guardian_id)
            
            if not guardian:
                QMessageBox.warning(self, "تنبيه", "لم يتم العثور على بيانات الوصي.")
                return

            # ملء بيانات الوصي
            self.lineEdit_guardian_name.setText(guardian.name)
            self.lineEdit_guardian_nid.setText(guardian.national_id)
            self.lineEdit_guardian_phone.setText(guardian.phone)
            if guardian.appointment_date:
                self.dateEdit_guardian_appointment.setDate(QDate(
                    guardian.appointment_date.year,
                    guardian.appointment_date.month,
                    guardian.appointment_date.day
                ))
            self.comboBox_guardian_relationship.setCurrentIndex(guardian.relationship)

            # ملء جدول الأيتام (للعرض فقط)
            table = self.tableWidget_guardian_orphans
            table.setColumnCount(6) # Add one column for Age
            table.setHorizontalHeaderLabels(["ID", "الاسم", "رقم الهوية", "تاريخ الميلاد", "الجنس", "العمر"])
            table.setColumnHidden(0, True) # Hide ID column
            table.setRowCount(len(orphans))
            
            for row_idx, orphan in enumerate(orphans):
                # ID (مخفي)
                table.setItem(row_idx, 0, QTableWidgetItem(str(orphan.id)))
                # الاسم
                table.setItem(row_idx, 1, QTableWidgetItem(orphan.name or ""))
                # رقم الهوية
                table.setItem(row_idx, 2, QTableWidgetItem(orphan.national_id or ""))

                # تاريخ الميلاد (عرض كنص فقط)
                dob_text = orphan.date_of_birth.strftime("%d/%m/%Y") if orphan.date_of_birth else ""
                table.setItem(row_idx, 3, QTableWidgetItem(dob_text))

                # الجنس (عرض كنص فقط)
                gender_map = {1: "ذكر", 2: "أنثى"}
                gender_text = gender_map.get(orphan.gender, "غير محدد")
                table.setItem(row_idx, 4, QTableWidgetItem(gender_text))
                
                # العمر المحسوب
                if orphan.date_of_birth:
                    today = date.today()
                    age = today.year - orphan.date_of_birth.year - ((today.month, today.day) < (orphan.date_of_birth.month, orphan.date_of_birth.day))
                    table.setItem(row_idx, 5, QTableWidgetItem(str(age)))
                else:
                    table.setItem(row_idx, 5, QTableWidgetItem("-"))
                
                # جعل الصفوف غير قابلة للتعديل
                for col in range(table.columnCount()):
                    item = table.item(row_idx, col)
                    if item:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    else:
                        # Ensure all cells are created before setting flags
                        item = QTableWidgetItem()
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        table.setItem(row_idx, col, item)

            # تخزين ID الوصي الحالي وتفعيل زر التعديل
            self.current_guardian_id = guardian_id
            self.pushButton_guardian_update.setEnabled(True)

            # تفعيل زر تصدير التقرير
            try:
                self.export_report_2.setEnabled(True)
            except Exception:
                pass
            
            # الانتقال لتبويب ملف الوصي (نفترض أنه التبويب الفرعي رقم 1 في تبويب الأوصياء)
            # self.tabWidget_guardians.setCurrentIndex(1) # تحتاج إلى معرفة اسم أداة التبويب الفرعية

        except Exception as e:
            print(f"Error loading guardian details: {e}")
            QMessageBox.critical(self, "خطأ", f"فشل عرض بيانات الوصي:\n{str(e)}")

    def update_guardian(self):
        """تعديل بيانات الوصي فقط."""
        if self.current_guardian_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد وصي للتعديل أولاً.")
            return

        try:
            # 1. استخراج بيانات الوصي
            guardian_data = self.get_guardian_form_data()
            
            # 2. استدعاء دالة التحديث في طبقة الخدمة (تم تعديلها لتقبل بيانات الوصي فقط)
            self.db_service.update_guardian_and_orphans(
                self.current_guardian_id, 
                guardian_data
            )
            
            # 3. عرض رسالة نجاح وتحديث العرض
            QMessageBox.information(self, "نجاح", "تم تحديث بيانات الوصي بنجاح.")
            self.clear_guardian_form()
            self.load_guardians_list()
            self.tabWidget_4.setCurrentIndex(0)

        except ValueError as ve:
            QMessageBox.warning(self, "تحقق من البيانات", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "خطأ في التعديل", f"فشل تعديل بيانات الوصي:\n{str(e)}")
            print(f"Error updating guardian: {e}")

    def delete_deceased(self):
        """حذف متوفى محدد."""
        if self.current_deceased_id is None:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد متوفى للحذف أولاً.")
            return

        reply = QMessageBox.question(self, 'تأكيد الحذف', 
            "هل أنت متأكد من حذف هذا المتوفى وجميع الأيتام المرتبطين به؟", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db_service.delete_deceased(self.current_deceased_id)
                self.clear_deceased_form()
                self.load_deceaseds()
                try:
                    self.update_dashboard_charts()
                except Exception as e:
                    print(f"Warning: failed to update dashboard charts after delete_deceased: {e}")
                QMessageBox.information(self, "نجاح", "تم حذف المتوفى والأيتام المرتبطين بنجاح.")
            except Exception as e:
                print(f"Error deleting deceased: {e}")
                QMessageBox.critical(self, "خطأ", f"فشل عملية الحذف:\n{str(e)}")

    # ==================================================
    # دوال التعامل مع جدول الأيتام (داخل نموذج الإدخال)
    # ==================================================

    def add_row_to_orphans_table(self):
        """إضافة صف جديد فارغ لجدول الأيتام."""
        table = self.tableWidget
        current_row_count = table.rowCount()
        table.insertRow(current_row_count)
        
        # إضافة QTableWidgetItem فارغ لـ ID, الاسم, رقم الهوية
        table.setItem(current_row_count, 0, QTableWidgetItem("")) # ID
        table.setItem(current_row_count, 1, QTableWidgetItem("")) # الاسم
        table.setItem(current_row_count, 2, QTableWidgetItem("")) # رقم الهوية
        
        # إضافة QDateEdit لتاريخ الميلاد
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd/MM/yyyy")
        date_edit.setDate(QDate(date.today().year - 10, 1, 1)) # تاريخ افتراضي
        table.setCellWidget(current_row_count, 3, date_edit)

        # إضافة QComboBox للجنس
        combo = QComboBox()
        combo.addItems(["اختر", "ذكر", "أنثى"])
        table.setCellWidget(current_row_count, 4, combo)

    def delete_selected_orphan_row(self):
        """حذف الصف المحدد من جدول الأيتام."""
        table = self.tableWidget
        row = table.currentRow()

        if row == -1:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد صف للحذف")
            return

        table.removeRow(row)

    def add_row_to_transactions_table(self):
        """إضافة صف جديد فارغ لجدول العمليات."""
        table = self.tableWidget_4
        current_row_count = table.rowCount()
        table.insertRow(current_row_count)
        
        combo_currency = QComboBox()
        currencies = self.db_service.get_currency_names()
        combo_currency.addItems(['اختر']+[c.name for c in currencies])
        table.setCellWidget(current_row_count, 1, combo_currency)
        
        combo_transaction_type = QComboBox()
        combo_transaction_type.addItems(["اختر","إيداع", "سحب"])
        table.setCellWidget(current_row_count, 2, combo_transaction_type)
        
        table.setItem(current_row_count, 3, QTableWidgetItem(""))
        
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd/MM/yyyy")
        date_edit.setDate(QDate.currentDate()) # تاريخ افتراضي
        table.setCellWidget(current_row_count, 4, date_edit)

        table.setItem(current_row_count, 5, QTableWidgetItem(""))

    def delete_selected_transaction_row(self):
        """حذف الصف المحدد من جدول العمليات. إذا كانت العملية موجودة في DB سيتم تأكيد الحذف ثم حذفها وتحديث الأرصدة."""
        table = self.tableWidget_4
        row = table.currentRow()

        if row == -1:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد صف للحذف")
            return

        tx_id_item = table.item(row, 0)
        tx_id = int(tx_id_item.text()) if tx_id_item and tx_id_item.text().isdigit() else None

        if tx_id and hasattr(self, "current_orphan_id") and self.current_orphan_id:
            reply = QMessageBox.question(
                self, "تأكيد الحذف",
                f"هل أنت متأكد من حذف العملية رقم {tx_id}؟ هذا سيُحدّث رصيد اليتيم تلقائياً.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    self.db_service.delete_transaction(tx_id)
                    QMessageBox.information(self, "نجاح", "تم حذف العملية وتحديث الرصيد.")
                    # إعادة تحميل بيانات اليتيم لإظهار التغييرات
                    self.load_orphan_details(self.current_orphan_id)
                except Exception as e:
                    QMessageBox.critical(self, "خطأ في الحذف", str(e))
        else:
            # لم يكن للصف عملية مخزنة، فقط ازله من الواجهة
            table.removeRow(row)

    # ==================================================
    # دوال CRUD للأيتام (فارغة في الكود الأصلي)
    # ==================================================
    
    def add_orphan(self):
        pass
    
    def update_orphan(self):
        if not hasattr(self, "current_orphan_id"):
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار يتيم أولًا")
            return

        try:
            # 1️⃣ بيانات اليتيم
            orphan_data = self.get_orphan_form_data()

            # 2️⃣ العمليات
            transactions_data = self.get_transactions_table_data()

            # 2.a) كشف العمليات المحذوفة (مقارنة القاعدة مقابل ما هو في الجدول)
            try:
                existing_transactions = self.db_service.get_orphan_transactions(self.current_orphan_id)
                existing_ids = set([t["id"] for t in existing_transactions if t.get("id")])
                incoming_ids = set([tx.get("id") for tx in transactions_data if tx.get("id")])
                deleted_ids = existing_ids - incoming_ids
                for del_id in deleted_ids:
                    # حذف كل عملية مفقودة من الواجهة
                    self.db_service.delete_transaction(del_id)
            except Exception as e:
                # إذا فشل الفحص، لا نوقف العملية، لكن نُعلم المستخدم
                print(f"Warning: failed to compute deleted transactions: {e}")

            # 3️⃣ تحديث بيانات اليتيم
            self.db_service.update_orphan_basic_data(
                self.current_orphan_id,
                orphan_data
            )

            # 4️⃣ تحديث / إضافة العمليات
            for tx in transactions_data:
                if tx.get("id"):
                    self.db_service.update_transaction(tx)
                else:
                    self.db_service.add_transaction(
                        orphan_id=self.current_orphan_id,
                        transaction_data=tx
                    )

            # 5️⃣ إعادة تحميل البيانات في الواجهة
            self.load_orphan_details(self.current_orphan_id)
            try:
                self.update_dashboard_charts()
            except Exception as e:
                print(f"Warning: failed to update dashboard charts after update_orphan: {e}")

            QMessageBox.information(self, "تم", "تم تحديث بيانات اليتيم بنجاح")

        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))
    def delete_orphan(self):
        pass

def main():
    """Create the QApplication, install global filters, and show MainWindow."""
    app = QApplication(sys.argv)

    # Global Input Behavior Filter (prevents unwanted wheel events and enforces date format)
    global_filter = GlobalInputBehaviorFilter()
    app.installEventFilter(global_filter)

    # Show window
    window = MainWindow()
    window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()