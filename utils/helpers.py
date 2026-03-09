import os
from PyQt6.QtCore import QObject, QEvent, QLocale
from PyQt6.QtWidgets import QComboBox, QDateEdit, QCalendarWidget, QApplication
from datetime import date, datetime
from PyQt6.QtGui import QFontDatabase, QFont
from decimal import Decimal
from PyQt6.QtCore import QDate

from database.models import ActivityLog

# مسار جذر المشروع (لملفات الأصول)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def validate_date(date_text: str, required=True) -> QDate | None:
    """
    يتحقق من التاريخ بصيغة dd/MM/yyyy
    - required: هل الحقل إجباري أم لا
    """
    if not date_text:
        if required:
            raise ValueError("حقل التاريخ إجباري")
        return None

    date = QDate.fromString(date_text, "dd/MM/yyyy")
    if not date.isValid():
        raise ValueError("صيغة التاريخ غير صحيحة، يجب أن تكون 'سنة/شهر/يوم'")

    return date


def qdate_to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


def parse_decimal(s: str, field_name: str = "قيمة", required: bool = False) -> Decimal:
    """Parse a numeric string into Decimal, disallow negative values.

    - s: the input string (may contain commas)
    - field_name: used in error messages (Arabic)
    - required: if True, empty string raises an error
    """
    if s is None or (isinstance(s, str) and s.strip() == ""):
        if required:
            raise ValueError(f"يرجى إدخال {field_name}")
        return Decimal(0)

    s_clean = str(s).replace(',', '').strip()
    try:
        val = Decimal(s_clean)
    except Exception:
        raise ValueError(f"يرجى إدخال قيمة رقمية صحيحة للحقل {field_name}")

    if val < 0:
        raise ValueError(f"القيمة لا يمكن أن تكون سالبة للحقل {field_name}")

    return val


def load_cairo_fonts():
    """
    تحميل جميع أوزان خط Cairo وإرجاع اسم العائلة
    """
    fonts_path = os.path.join(PROJECT_ROOT, "assets", "fonts")
    font_files = [
        "Cairo-Regular.ttf",
        "Cairo-Bold.ttf",
        "Cairo-Light.ttf",
        "Cairo-Medium.ttf",
        "Cairo-SemiBold.ttf",
        "Cairo-ExtraBold.ttf",
    ]

    for file in font_files:
        font_path = os.path.join(fonts_path, file)
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id == -1:
            print(f"Failed to load font: {file}")

    font_families = QFontDatabase.applicationFontFamilies(font_id)
    if font_families:
        return font_families[0]
    return None


def apply_global_font(app: QApplication, font_family: str, font_size: int = 10):
    """
    تعيين الخط لجميع عناصر التطبيق تلقائيًا
    """
    app.setFont(QFont(font_family, font_size))
    app.setStyleSheet(f"""
        QWidget {{
            font-family: "{font_family}";
        }}
    """)


class GlobalInputBehaviorFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QDateEdit, QCalendarWidget)):
                event.ignore()
                return True

        if isinstance(obj, QComboBox):
            obj.setLocale(QLocale(QLocale.Language.English))

        return super().eventFilter(obj, event)


def parse_and_validate_date(date_str):
    """
    تتحقق من التنسيق وتحول النص إلى كائن تاريخ صالح لقاعدة البيانات.
    التنسيق المتوقع: DD/MM/YYYY
    """
    if not date_str or not date_str.strip():
        return None

    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    raise ValueError(f"التاريخ '{date_str}' غير صالح. يرجى استخدام التنسيق: سنة/شهر/يوم")


def calculate_age(birth_date):
    if not birth_date:
        return "---"
    today = datetime.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def log_activity(session, user_id, action, resource_type, resource_id=None, description=""):
    try:
        new_log = ActivityLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description
        )
        session.add(new_log)
        session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        session.rollback()


def try_get_date(text):
    if text == '//':
        return None
    return text

def validate_nid(nid: str):
    """Validate that the national ID is exactly 9 digits if enterd."""
    if nid and (not nid.isdigit() or len(nid) != 9):
        raise ValueError("رقم الهوية غير صالح (يجب أن يكون 9 أرقام)")
    return nid or None
