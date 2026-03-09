#!/usr/bin/env python
"""سكريبت لإنشاء أيقونة التطبيق"""

import os
import sys
from pathlib import Path

# التحقق من توفر Pillow
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("يتحتاج التطبيق إلى مكتبة Pillow. جاري التثبيت...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw, ImageFont

def create_app_icon():
    """إنشاء أيقونة التطبيق"""
    
    # تحديد مسار الأيقونة
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    icon_path = assets_dir / "app_icon.png"
    
    # إذا كانت الأيقونة موجودة بالفعل، تخطيها
    if icon_path.exists():
        print(f"✓ الأيقونة موجودة بالفعل: {icon_path}")
        return
    
    # إنشاء صورة جديدة (256x256) بلون أزرق متدرج
    size = 256
    image = Image.new('RGBA', (size, size), color='white')
    draw = ImageDraw.Draw(image)
    
    # رسم خلفية زرقاء
    blue_color = (66, 133, 244)  # Google Blue
    draw.rectangle([0, 0, size, size], fill=blue_color)
    
    # رسم نص (الحرف الأول: ي من يتيم)
    try:
        # محاولة استخدام خط عربي (إذا كان موجوداً)
        font = ImageFont.truetype("C:\\Windows\\Fonts\\Cairo-Bold.ttf", 120)
    except:
        # استخدام الخط الافتراضي إذا لم يكن الخط العربي موجوداً
        font = ImageFont.load_default()
    
    # رسم الحرف في المنتصف
    text = "ي"  # الحرف الأول من "يتيم"
    text_color = 'white'
    
    # حساب موضع النص
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 10
    
    draw.text((x, y), text, font=font, fill=text_color)
    
    # حفظ الأيقونة
    image.save(icon_path, 'PNG')
    print(f"✓ تم إنشاء الأيقونة بنجاح: {icon_path}")
    
    # إنشاء نسخة ICO أيضاً
    ico_path = assets_dir / "app_icon.ico"
    try:
        image.save(ico_path, 'ICO')
        print(f"✓ تم إنشاء نسخة ICO: {ico_path}")
    except Exception as e:
        print(f"⚠ لم يتم إنشاء نسخة ICO: {str(e)}")

if __name__ == "__main__":
    try:
        create_app_icon()
        print("\n✅ تم إنشاء الأيقونات بنجاح!")
    except Exception as e:
        print(f"❌ خطأ في إنشاء الأيقونة: {str(e)}")
        sys.exit(1)
