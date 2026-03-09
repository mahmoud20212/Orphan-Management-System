"""
نقطة الدخول الرئيسية للتطبيق.
تشغيل التطبيق: python main.py
"""
import sys
from app import main

if __name__ == "__main__":
    sys.exit(main() or 0)
