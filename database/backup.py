import os
import sys
import subprocess
from datetime import datetime
from PyQt6.QtWidgets import (QFileDialog, QMessageBox, QProgressDialog, 
                             QMainWindow, QPushButton, QVBoxLayout, QWidget, QApplication)
from PyQt6.QtCore import QThread, pyqtSignal

# --- 1. الخيط المسؤول عن العمليات الثقيلة (Worker) ---
class DatabaseWorker(QThread):
    # نعدل الإشارة لتشمل (النجاح، الرسالة، والنمط)
    finished = pyqtSignal(bool, str, str) 

    def __init__(self, command, file_path, mode="backup"):
        super().__init__()
        self.command = command
        self.file_path = file_path
        self.mode = mode

    def run(self):
        try:
            if self.mode == "backup":
                with open(self.file_path, "w", encoding="utf-8") as f:
                    result = subprocess.run(self.command, stdout=f, stderr=subprocess.PIPE, shell=True, text=True)
            else:
                full_command = f'{self.command} < "{self.file_path}"'
                result = subprocess.run(full_command, stderr=subprocess.PIPE, shell=True, text=True)

            if result.returncode == 0:
                # نرسل النمط (mode) مع إشارة الانتهاء
                self.finished.emit(True, "تمت العملية بنجاح", self.mode)
            else:
                self.finished.emit(False, result.stderr, self.mode)
        except Exception as e:
            self.finished.emit(False, str(e), self.mode)

# --- 2. مدير النسخ الاحتياطي (Backup Manager) ---
class BackupManager:
    def __init__(self, parent, db_name="mydb", user="root", password="root"):
        self.parent = parent
        self.db_name = db_name
        self.user = user
        self.password = password

    def execute_backup(self):
        default_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        file_path, _ = QFileDialog.getSaveFileName(self.parent, "حفظ النسخة", default_name, "SQL Files (*.sql)")
        
        if file_path:
            cmd = f'mysqldump -u{self.user} -p"{self.password}" --opt --single-transaction {self.db_name}'
            self._start_thread(cmd, file_path, "backup")

    def execute_restore(self):
        file_path, _ = QFileDialog.getOpenFileName(self.parent, "اختر نسخة للاستعادة", "", "SQL Files (*.sql)")
        
        if file_path:
            confirm = QMessageBox.warning(
                self.parent, "تنبيه نهائي",
                "سيتم الآن إجبار القاعدة على الاستجابة وإعادة تشغيل البرنامج.\nهل أنت متأكد؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if confirm == QMessageBox.StandardButton.Yes:
                # 1. بناء أمر "انتحاري" لقتل كل العمليات العالقة على القاعدة قبل الاستعادة
                # هذا الأمر يبحث عن كل الـ IDs التابعة للقاعدة ويقتلها
                kill_sessions_cmd = (
                    f'mysql -u{self.user} -p"{self.password}" -e '
                    f'"SELECT GROUP_CONCAT(id) FROM information_schema.processlist WHERE db=\'{self.db_name}\'" -s -N'
                )
                
                try:
                    res = subprocess.run(kill_sessions_cmd, shell=True, capture_output=True, text=True)
                    ids = res.stdout.strip()
                    if ids and ids != "NULL":
                        for session_id in ids.split(','):
                            subprocess.run(f'mysql -u{self.user} -p"{self.password}" -e "KILL {session_id}"', shell=True)
                except: pass # إذا فشل القتل نكمل للاستعادة

                # 2. تنفيذ الاستعادة مع ميزة 'Batch Mode' لإيقاف التفاعل الذي يسبب البطء
                cmd = f'mysql -u{self.user} -p"{self.password}" --batch --force --max_allowed_packet=1G {self.db_name}'
                self._start_thread(cmd, file_path, "restore")

    def _start_thread(self, cmd, path, mode):
        # تخصيص نص رسالة التحميل حسب النوع
        msg = "جاري استعادة البيانات.. يرجى الانتظار" if mode == "restore" else "جاري إنشاء نسخة احتياطية.."
        
        self.progress = QProgressDialog(msg, None, 0, 0, self.parent)
        self.progress.setWindowTitle("نظام قاعدة البيانات")
        self.progress.setModal(True)
        self.progress.show()

        self._toggle_buttons(False)

        self.worker = DatabaseWorker(cmd, path, mode)
        # نربط الإشارة مباشرة بدون lambda
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, success, message, mode):
        self.progress.close()
        
        if success:
            if mode == "restore":
                QMessageBox.information(self.parent, "استعادة البيانات", "تمت الاستعادة بنجاح. سيتم إعادة تشغيل التطبيق.")
                self.restart_application()
            else:
                QMessageBox.information(self.parent, "نسخ احتياطي", "تم إنشاء النسخة الاحتياطية بنجاح.")
                self._toggle_buttons(True)
        else:
            # تخصيص عنوان الخطأ حسب النوع
            title = "فشل الاستعادة" if mode == "restore" else "فشل النسخ الاحتياطي"
            QMessageBox.critical(self.parent, title, f"حدث خطأ:\n{message}")
            self._toggle_buttons(True)

    def _toggle_buttons(self, state):
        if hasattr(self.parent, 'btn_backup'): self.parent.btn_backup.setEnabled(state)
        if hasattr(self.parent, 'btn_restore_backup'): self.parent.btn_restore_backup.setEnabled(state)

    def restart_application(self):
        """إعادة تشغيل البرنامج لضمان تحديث الاتصالات والبيانات"""
        python = sys.executable
        os.execl(python, python, *sys.argv)

# # --- 3. النافذة الرئيسية ---
# class MainWindow(QMainWindow):
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("نظام الإدارة - النسخ والاستعادة")
#         self.resize(400, 150)

#         # تعريف الأزرار (تأكد من تسميتها كما في BackupManager)
#         self.btn_backup = QPushButton("إنشاء نسخة احتياطية (Backup)")
#         self.btn_restore_backup = QPushButton("استعادة نسخة قديمة (Restore)")

#         # إعداد المدير - ضع بياناتك هنا
#         self.backup_manager = BackupManager(self, db_name="mydb", user="root", password="your_password")

#         self.btn_backup.clicked.connect(self.backup_manager.execute_backup)
#         self.btn_restore_backup.clicked.connect(self.backup_manager.execute_restore)

#         layout = QVBoxLayout()
#         layout.addWidget(self.btn_backup)
#         layout.addWidget(self.btn_restore_backup)
#         container = QWidget()
#         container.setLayout(layout)
#         self.setCentralWidget(container)

# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     window.show()
#     sys.exit(app.exec())