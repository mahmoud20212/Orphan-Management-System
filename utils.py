from PyQt6.QtCore import QObject, QEvent, QLocale
from PyQt6.QtWidgets import QComboBox, QDateEdit, QCalendarWidget
from datetime import date

def calculate_age(born: date) -> int:
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age

class GlobalInputBehaviorFilter(QObject):
    """
    فلتر عام للتحكم بسلوك الإدخالات في التطبيق.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QDateEdit, QCalendarWidget)):
                event.ignore()
                return True

        if event.type() == QEvent.Type.Show:
            if isinstance(obj, QDateEdit):
                obj.setDisplayFormat("yyyy/MM/dd")
                obj.setCalendarPopup(True)
                obj.setLocale(QLocale(QLocale.Language.English))

        if isinstance(obj, QComboBox):
            obj.setLocale(QLocale(QLocale.Language.English))

        return super().eventFilter(obj, event)