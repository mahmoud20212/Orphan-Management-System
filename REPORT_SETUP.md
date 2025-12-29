# Report generation dependencies & setup

To enable PDF export you need either:

1) WeasyPrint (recommended):
   - pip install weasyprint
   - On Windows: WeasyPrint requires additional system libraries (Cairo, Pango). See https://weasyprint.org/docs/install/#windows

or

2) wkhtmltopdf + pdfkit:
   - Install wkhtmltopdf binary for Windows and add to PATH: https://wkhtmltopdf.org/downloads.html
   - pip install pdfkit

Also required for templates:
- Jinja2 (pip install jinja2)

Notes:
- After installing WeasyPrint, the report feature will render PDFs directly.
- If using wkhtmltopdf, ensure the binary is accessible in PATH or configure pdfkit.configuration with its path.
