"""
مساعد توليد نصوص الملاحظات الواضحة والموحدة للحركات المالية
Clarity-focused note generator for financial transactions
"""

def generate_transaction_note(transaction_type: str, details: dict = None) -> str:
    """
    توليد ملاحظة واضحة وموحدة للحركات المالية
    
    Args:
        transaction_type: نوع الحركة ('orphan_share', 'distribution', 'deposit', 'withdrawal', etc.)
        details: قاموس يحتوي على التفاصيل الإضافية
    
    Returns:
        نص الملاحظة
    """
    if details is None:
        details = {}
    
    # ملاحظة: حصة اليتيم من المتوفى
    if transaction_type == 'orphan_share':
        deceased_name = details.get('deceased_name', 'غير محدد')
        orphan_name = details.get('orphan_name', '')
        currency = details.get('currency', '')
        amount = details.get('amount', 0)
        
        if orphan_name:
            return f"حصة يتيم: {orphan_name} من {deceased_name} ({amount} {currency})"
        return f"حصة من المتوفى: {deceased_name} ({amount} {currency})"
    
    # ملاحظة: توزيع الأرصدة عند إنشاء الملف
    elif transaction_type == 'initial_distribution':
        deceased_name = details.get('deceased_name', 'غير محدد')
        distribution_mode = details.get('mode', 'غير محدد')
        currency = details.get('currency', '')
        amount = details.get('amount', 0)
        orphans_count = details.get('orphans_count', 0)
        
        mode_text = _get_mode_text(distribution_mode)
        return f"توزيع أولي ({mode_text}) من {deceased_name} على {orphans_count} أيتام ({amount} {currency})"
    
    # ملاحظة: سحب من رصيد المتوفى (توزيع)
    elif transaction_type == 'deceased_withdrawal':
        deceased_name = details.get('deceased_name', 'غير محدد')
        currency = details.get('currency', '')
        amount = details.get('amount', 0)
        orphans_count = details.get('orphans_count', 0)
        
        return f"سحب جزئي من {deceased_name} لتوزيع على {orphans_count} أيتام ({amount} {currency})"
    
    # ملاحظة: توزيع مستمر أو إضافي
    elif transaction_type == 'ongoing_distribution':
        deceased_name = details.get('deceased_name', 'غير محدد')
        distribution_mode = details.get('mode', 'تلقائي')
        currency = details.get('currency', '')
        amount = details.get('amount', 0)
        
        mode_text = _get_mode_text(distribution_mode)
        return f"توزيع ({mode_text}) من رصيد المتوفى {deceased_name} ({amount} {currency})"
    
    # ملاحظة: إيداع عام
    elif transaction_type == 'deposit':
        payer_name = details.get('payer_name', '')
        amount = details.get('amount', 0)
        currency = details.get('currency', '')
        
        if payer_name:
            return f"إيداع من {payer_name} ({amount} {currency})"
        return f"إيداع ({amount} {currency})"
    
    # ملاحظة: سحب عام
    elif transaction_type == 'withdrawal':
        amount = details.get('amount', 0)
        currency = details.get('currency', '')
        reason = details.get('reason', '')
        
        if reason:
            return f"سحب لـ {reason} ({amount} {currency})"
        return f"سحب ({amount} {currency})"
    
    # ملاحظة: تحويل بين حسابات
    elif transaction_type == 'transfer':
        from_person = details.get('from_person', 'غير محدد')
        to_person = details.get('to_person', 'غير محدد')
        amount = details.get('amount', 0)
        currency = details.get('currency', '')
        
        return f"تحويل من {from_person} إلى {to_person} ({amount} {currency})"
    
    # ملاحظة: تصحيح أو تعديل
    elif transaction_type == 'correction':
        reason = details.get('reason', 'تصحيح')
        amount = details.get('amount', 0)
        currency = details.get('currency', '')
        
        return f"تصحيح - {reason} ({amount} {currency})"
    
    # افتراضي
    else:
        return details.get('default_text', 'حركة مالية')


def _get_mode_text(mode: str) -> str:
    """تحويل رمز الطريقة إلى نص واضح"""
    modes = {
        'equal': 'بالتساوي',
        'بالتساوي': 'بالتساوي',
        'male_double': 'الذكر مثل حظ الأنثيين',
        'ذكر مثل حظ الانثيين': 'الذكر مثل حظ الأنثيين',
        'manual': 'يدوي',
        'يدوي': 'يدوي',
        'auto': 'تلقائي',
        'تلقائي': 'تلقائي',
    }
    return modes.get(mode, mode)


def generate_deceased_transaction_note(
    transaction_type: str, 
    amount: float,
    currency_name: str,
    distribution_mode: str = '',
    receipt_details: dict = None
) -> str:
    """
    توليد ملاحظة واضحة لحركات المتوفى
    
    Args:
        transaction_type: 'deposit' أو 'withdraw'
        amount: المبلغ
        currency_name: اسم العملة
        distribution_mode: طريقة التوزيع إن وجدت
        receipt_details: تفاصيل السند (رقم السند، اسم المودع، إلخ)
    
    Returns:
        نص الملاحظة الموحد
    """
    if receipt_details is None:
        receipt_details = {}
    
    amount_str = f"{amount:,.2f} {currency_name}"
    
    if transaction_type == 'deposit':
        payer = receipt_details.get('payer_name', '').strip()
        receipt_num = receipt_details.get('receipt_number', '').strip()
        
        text_parts = ['إيداع', amount_str]
        if payer:
            text_parts.append(f"من {payer}")
        if receipt_num:
            text_parts.append(f"[سند: {receipt_num}]")
        
        return ' - '.join(text_parts)
    
    elif transaction_type == 'distribute':
        mode = _get_mode_text(distribution_mode)
        return f"توزيع ({mode}) - {amount_str}"
    
    else:
        return f"{transaction_type} - {amount_str}"


def generate_orphan_transaction_note(
    transaction_type: str,
    amount: float,
    currency_name: str,
    orphan_name: str = '',
    deceased_name: str = '',
    from_source: str = ''
) -> str:
    """
    توليد ملاحظة واضحة لحركات الأيتام
    
    Args:
        transaction_type: 'deposit' أو 'withdraw'
        amount: المبلغ
        currency_name: اسم العملة
        orphan_name: اسم اليتيم
        deceased_name: اسم المتوفى (إن وجد)
        from_source: مصدر الحركة
    
    Returns:
        نص الملاحظة الموحد
    """
    amount_str = f"{amount:,.2f} {currency_name}"
    
    if transaction_type == 'deposit':
        if from_source:
            if 'متوفى' in from_source or deceased_name:
                return f"إيداع من رصيد المتوفى - {amount_str}"
            else:
                return f"إيداع من {from_source} - {amount_str}"
        return f"إيداع - {amount_str}"
    
    elif transaction_type == 'withdraw':
        if from_source:
            return f"سحب لـ {from_source} - {amount_str}"
        return f"سحب - {amount_str}"
    
    else:
        return f"{transaction_type} - {amount_str}"


def format_note_for_display(note: str, max_length: int = 80) -> str:
    """
    تنسيق الملاحظة لعرضها في الواجهة
    
    Args:
        note: نص الملاحظة
        max_length: الحد الأقصى لعدد الأحرف قبل الاختصار
    
    Returns:
        النص المنسق
    """
    if not note:
        return ''
    
    note = note.strip()
    if len(note) > max_length:
        return note[:max_length-3] + '...'
    
    return note
