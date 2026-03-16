import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QStackedLayout
)
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modern Dashboard")
        self.resize(1000, 600)

        # ===== Sidebar =====
        self.sidebar = QFrame()
        self.sidebar.setStyleSheet("background-color: #2c3e50;")
        self.sidebar.setMaximumWidth(70)

        # Sidebar buttons
        self.btn_home = QPushButton("🏠")
        self.btn_dashboard = QPushButton("📊")
        self.btn_settings = QPushButton("⚙")
        for btn in [self.btn_home, self.btn_dashboard, self.btn_settings]:
            btn.setStyleSheet("color:white; font-size:18px; border:none; padding:15px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.toggle_btn = QPushButton("☰")
        self.toggle_btn.setStyleSheet("color:white; font-size:20px; border:none; padding:10px;")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_sidebar)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.addWidget(self.toggle_btn)
        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(self.btn_home)
        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addStretch()

        # ===== Header =====
        self.header = QFrame()
        self.header.setStyleSheet("background-color:#34495e;")
        self.header.setFixedHeight(60)
        header_layout = QHBoxLayout(self.header)
        header_label = QLabel("Dashboard Header")
        header_label.setStyleSheet("color:white; font-size:20px; font-weight:bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        # ===== Main Content Area =====
        self.content = QFrame()
        self.content.setStyleSheet("background-color:#ecf0f1;")
        self.stack_layout = QStackedLayout(self.content)

        # Pages
        self.page_home = QLabel("Home Page Content")
        self.page_home.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_dashboard = QLabel("Dashboard Page Content")
        self.page_dashboard.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_settings = QLabel("Settings Page Content")
        self.page_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stack_layout.addWidget(self.page_home)
        self.stack_layout.addWidget(self.page_dashboard)
        self.stack_layout.addWidget(self.page_settings)

        # Connect sidebar buttons to pages
        self.btn_home.clicked.connect(lambda: self.stack_layout.setCurrentIndex(0))
        self.btn_dashboard.clicked.connect(lambda: self.stack_layout.setCurrentIndex(1))
        self.btn_settings.clicked.connect(lambda: self.stack_layout.setCurrentIndex(2))

        # ===== Layouts =====
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.sidebar)
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.header)
        right_layout.addWidget(self.content)
        main_layout.addLayout(right_layout)

        # ===== Animation =====
        self.anim_sidebar = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.anim_sidebar.setDuration(300)
        self.anim_sidebar.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self.sidebar_open = False

    def toggle_sidebar(self):
        if self.sidebar_open:
            self.anim_sidebar.setStartValue(200)
            self.anim_sidebar.setEndValue(70)
        else:
            self.anim_sidebar.setStartValue(70)
            self.anim_sidebar.setEndValue(200)
        self.anim_sidebar.start()
        self.sidebar_open = not self.sidebar_open


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Dashboard()
    window.show()
    sys.exit(app.exec())