"""Application entrypoint shim.

This file keeps a minimal main() compatible with previous usage while the
real MainWindow implementation lives in views.main_view as part of the refactor.
"""
from PyQt6.QtWidgets import QApplication
import sys

# Import the refactored MainWindow and the global event filter
from views.main_view import MainWindow, GlobalInputBehaviorFilter


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
