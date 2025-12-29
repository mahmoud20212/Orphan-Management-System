"""
Compatibility shim for legacy imports.
This file re-exports the public API from `services.reporting` so existing imports keep working
while the implementation lives in the `services` package.
"""

from services.reporting import (
    generate_report,
    fetch_entity_data,
    fetch_monthly_minors,
    ReportError,
    _render_html,
    TEMPLATE_MAP,
    RENDERER,
)

__all__ = [
    'generate_report',
    'fetch_entity_data',
    'fetch_monthly_minors',
    'ReportError',
    '_render_html',
    'TEMPLATE_MAP',
    'RENDERER',
]

