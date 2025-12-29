"""
Report generation service module.
This module contains the richer, well-organized report generation logic.
This module replaces the previous `report_service.py` implementation.
"""
from jinja2 import Environment, FileSystemLoader
import os
from datetime import date, datetime
from pathlib import Path

# Try to use WeasyPrint, else pdfkit
try:
    from weasyprint import HTML
    RENDERER = "weasy"
except Exception:
    try:
        import pdfkit
        RENDERER = "pdfkit"
    except Exception:
        RENDERER = None

from repositories.db_repository import DBService

# Initialize Jinja environment pointing to project templates folder
try:
    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")))
except Exception:
    env = None

TEMPLATE_MAP = {
    "orphan": "orphan_report.html",
    "deceased": "family_report.html",
    "guardian": "family_report.html",
    "monthly_minors": "monthly_minors_report.html",
}


def _format_date(d):
    if not d:
        return ""
    if isinstance(d, date):
        return d.strftime("%Y/%m/%d")
    try:
        return d.strftime("%Y/%m/%d")
    except Exception:
        return str(d)


class ReportError(Exception):
    pass


def _balances_summary(balances):
    totals = {}
    for b in balances:
        cur = b.currency.name
        totals[cur] = totals.get(cur, 0) + float(b.balance)
    return [{"currency": k, "amount": v} for k, v in totals.items()]


def _format_tx(t):
    def _g(x, a):
        if x is None:
            return None
        if isinstance(x, dict):
            return x.get(a)
        return getattr(x, a, None)
    
    print(t)
    
    return {
        "id": _g(t, 'id'),
        "type": "إيداع" if _g(t, 'type') == 'إيداع' else "سحب",
        "amount": float(_g(t, 'amount') or 0),
        "currency": _g(t, 'currency') or '',
        "date": _format_date(_g(t, 'date')),
        "note": _g(t, 'note') or ''
    }


def _get_attr(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def fetch_entity_data(entity_type: str, entity_id: int, db_service: DBService):
    """Return context dict for templates based on entity_type and id."""

    assets_dir = Path(os.path.join(os.path.dirname(__file__), "..", "assets", "images")).resolve()
    logo_file = (assets_dir / "logo.png")
    ps_logo_file = (assets_dir / "ps_logo.png")
    logo_path = logo_file.as_uri() if logo_file.exists() else None
    ps_logo_path = ps_logo_file.as_uri() if ps_logo_file.exists() else None

    ctx_common = {
        "generated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "organization": "مؤسسة إدارة وتنمية أموال اليتامى",
        "logo_path": logo_path,
        "ps_logo_path": ps_logo_path,
    }

    if not logo_path:
        print("[services.reporting] logo.png not found in assets/images; templates will not show organization logo.")
    if not ps_logo_path:
        print("[services.reporting] ps_logo.png not found in assets/images; Palestine emblem will not show.")

    if entity_type == "orphan":
        orphan = db_service.get_orphan_details(entity_id)
        if not orphan:
            raise ReportError("يتيم غير موجود")

        orphan_id = _get_attr(orphan, 'id')
        balances = db_service.get_orphan_balances(orphan_id)
        balances_list = [{"currency": b.currency.name, "amount": float(b.balance)} for b in balances]
        balances_total = _balances_summary(balances)
        txs = db_service.get_orphan_transactions(orphan_id)[:10]
        tx_list = [_format_tx(t) for t in txs]

        primary_guardian = next((link.guardian for link in getattr(orphan, 'guardian_links', []) if getattr(link, 'is_primary', False)), None)
        deceased = _get_attr(orphan, 'deceased')

        context = {
            **ctx_common,
            "orphan": {
                "id": _get_attr(orphan, 'id'),
                "name": _get_attr(orphan, 'name'),
                "birth_date": _format_date(_get_attr(orphan, 'date_of_birth')),
                "national_id": _get_attr(orphan, 'national_id'),
            },
            "balances": balances_list,
            "balances_total": balances_total,
            "transactions": tx_list,
            "deceased": None,
            "guardian": None,
        }

        if deceased:
            context["deceased"] = {
                "id": _get_attr(deceased, 'id'),
                "name": _get_attr(deceased, 'name'),
                "death_date": _format_date(_get_attr(deceased, 'date_of_death')),
                "national_id": _get_attr(deceased, 'national_id'),
            }

        if primary_guardian:
            context["guardian"] = {
                "id": _get_attr(primary_guardian, 'id'),
                "name": _get_attr(primary_guardian, 'name'),
                "national_id": _get_attr(primary_guardian, 'national_id'),
                "phone": _get_attr(primary_guardian, 'phone') or '',
                "appointment_date": _format_date(_get_attr(primary_guardian, 'appointment_date')),
            }

        return context

    if entity_type == "deceased":
        deceased, orphans, guardian = db_service.get_deceased_details(entity_id)
        if not deceased:
            raise ReportError("المتوفّى غير موجود")

        children = []
        for o in orphans:
            oid = _get_attr(o, 'id')
            balances = db_service.get_orphan_balances(oid)
            balances_list = [{"currency": b.currency.name, "amount": float(b.balance)} for b in balances]
            balances_total = _balances_summary(balances)
            txs = db_service.get_orphan_transactions(oid)[:5]
            tx_list = [_format_tx(t) for t in txs]
            children.append({
                "id": _get_attr(o, 'id'),
                "name": _get_attr(o, 'name'),
                "birth_date": _format_date(_get_attr(o, 'date_of_birth')),
                "national_id": _get_attr(o, 'national_id'),
                "balances": balances_list,
                "balances_total": balances_total,
                "recent_transactions": tx_list,
                "deceased": _get_attr(o, 'deceased')
            })

        context = {
            **ctx_common,
            "deceased": {
                "id": _get_attr(deceased, 'id'),
                "name": _get_attr(deceased, 'name'),
                "death_date": _format_date(_get_attr(deceased, 'date_of_death')),
                "national_id": _get_attr(deceased, 'national_id'),
            },
            "guardian": None,
            "children": children,
        }

        if guardian:
            context["guardian"] = {
                "id": _get_attr(guardian, 'id'),
                "name": _get_attr(guardian, 'name'),
                "national_id": _get_attr(guardian, 'national_id'),
                "phone": _get_attr(guardian, 'phone') or '',
                "appointment_date": _format_date(_get_attr(guardian, 'appointment_date')),
            }

        return context

    if entity_type == "guardian":
        guardian, orphans = db_service.get_guardian_details(entity_id)
        if not guardian:
            raise ReportError("الوصي غير موجود")

        children = []
        for o in orphans:
            oid = _get_attr(o, 'id')
            balances = db_service.get_orphan_balances(oid)
            balances_list = [{"currency": b.currency.name, "amount": float(b.balance)} for b in balances]
            balances_total = _balances_summary(balances)
            txs = db_service.get_orphan_transactions(oid)[:5]
            tx_list = [_format_tx(t) for t in txs]
            children.append({
                "id": _get_attr(o, 'id'),
                "name": _get_attr(o, 'name'),
                "birth_date": _format_date(_get_attr(o, 'date_of_birth')),
                "national_id": _get_attr(o, 'national_id'),
                "balances": balances_list,
                "balances_total": balances_total,
                "recent_transactions": tx_list,
                "deceased": _get_attr(o, 'deceased')
            })

        context = {
            **ctx_common,
            "guardian": {
                "id": _get_attr(guardian, 'id'),
                "name": _get_attr(guardian, 'name'),
                "national_id": _get_attr(guardian, 'national_id'),
                "phone": _get_attr(guardian, 'phone') or '',
                "appointment_date": _format_date(_get_attr(guardian, 'appointment_date')),
            },
            "children": children
        }

        return context

    raise ReportError("Unknown entity type")


def fetch_monthly_minors(months: int, db_service: DBService):
    """Prepare context for the monthly minors report template."""
    data = db_service.get_minors_count_by_month(months)
    return {
        "generated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "organization": "مؤسسة إدارة وتنمية أموال اليتامى",
        "months": months,
        "data": [ {"month": label, "count": cnt} for label, cnt in data ],
    }


def _render_html(entity_type: str, ctx: dict) -> str:
    if env is None:
        raise ReportError("Jinja2 is not installed. Install jinja2 to render templates.")
    template_name = TEMPLATE_MAP.get(entity_type)
    if not template_name:
        raise ReportError("No template configured for entity type")
    tmpl = env.get_template(template_name)
    return tmpl.render(**ctx)


def generate_report(entity_type: str, entity_id: int, output_path: str = None, as_bytes: bool = False):
    """Generate PDF report and write to output_path or return bytes if as_bytes=True.

    Args:
        entity_type: 'orphan'|'deceased'|'guardian'
        entity_id: integer id
        output_path: path to save PDF. If None and as_bytes True, returns bytes.
        as_bytes: if True and output_path is None, returns PDF bytes.
    """
    db = DBService()
    # For entity types that require an id we keep existing behaviour
    if entity_type == "monthly_minors":
        # here entity_id is treated as months
        months = int(entity_id)
        ctx = fetch_monthly_minors(months, db)
    else:
        ctx = fetch_entity_data(entity_type, entity_id, db)

    html = _render_html(entity_type, ctx)

    # Attempt to render PDF with available backend. If rendering fails, write the HTML to a temp file
    # so the user can inspect layout and CSS in a browser.
    import tempfile
    try:
        if RENDERER == "weasy":
            html_obj = HTML(string=html)
            if output_path:
                html_obj.write_pdf(output_path)
                return output_path
            else:
                return html_obj.write_pdf()
        elif RENDERER == "pdfkit":
            config = None
            try:
                config = pdfkit.configuration()
            except Exception:
                pass
            if output_path:
                pdfkit.from_string(html, output_path, configuration=config)
                return output_path
            else:
                return pdfkit.from_string(html, False, configuration=config)
        else:
            raise ReportError("No PDF rendering backend available. Install weasyprint or wkhtmltopdf/pdfkit.")
    except Exception as e:
        # Save rendered HTML for debugging
        try:
            tmp_dir = tempfile.gettempdir()
            fname = f"report_debug_{entity_type}_{entity_id}.html"
            tmp_path = os.path.join(tmp_dir, fname)
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            raise ReportError(f"فشل إنشاء PDF: {e}. تم حفظ نسخة HTML للتدقيق في: {tmp_path}")
        except ReportError:
            raise
        except Exception as e2:
            raise ReportError(f"فشل إنشاء PDF ({e}) ولم أتمكن من حفظ ملف HTML للتدقيق ({e2})") from e
    """Generate PDF report and write to output_path or return bytes if as_bytes=True.

    Args:
        entity_type: 'orphan'|'deceased'|'guardian'
        entity_id: integer id
        output_path: path to save PDF. If None and as_bytes True, returns bytes.
        as_bytes: if True and output_path is None, returns PDF bytes.
    """
    db = DBService()
    ctx = fetch_entity_data(entity_type, entity_id, db)
    html = _render_html(entity_type, ctx)

    # Attempt to render PDF with available backend. If rendering fails, write the HTML to a temp file
    # so the user can inspect layout and CSS in a browser.
    import tempfile
    try:
        if RENDERER == "weasy":
            html_obj = HTML(string=html)
            if output_path:
                html_obj.write_pdf(output_path)
                return output_path
            else:
                return html_obj.write_pdf()
        elif RENDERER == "pdfkit":
            config = None
            try:
                config = pdfkit.configuration()
            except Exception:
                pass
            if output_path:
                pdfkit.from_string(html, output_path, configuration=config)
                return output_path
            else:
                return pdfkit.from_string(html, False, configuration=config)
        else:
            raise ReportError("No PDF rendering backend available. Install weasyprint or wkhtmltopdf/pdfkit.")
    except Exception as e:
        # Save rendered HTML for debugging
        try:
            tmp_dir = tempfile.gettempdir()
            fname = f"report_debug_{entity_type}_{entity_id}.html"
            tmp_path = os.path.join(tmp_dir, fname)
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            raise ReportError(f"فشل إنشاء PDF: {e}. تم حفظ نسخة HTML للتدقيق في: {tmp_path}")
        except ReportError:
            raise
        except Exception as e2:
            raise ReportError(f"فشل إنشاء PDF ({e}) ولم أتمكن من حفظ ملف HTML للتدقيق ({e2})") from e