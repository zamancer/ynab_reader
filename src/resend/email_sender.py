import os
from typing import Any

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

import resend

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "templates"
)


def send_email(
    subject: str,
    recipients: list[str],
    html_content: str,
    sender: str = "YNAB Author <alan@zammx.com>",
):
    params: resend.Emails.SendParams = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html_content,
    }
    return resend.Emails.send(params)


def send_balance_alert_email(recipients: list[str], context: dict[str, Any]):
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("email_balance_alert.html")
    html_content = template.render(**context)
    subject = "Alerta de Diferencias de Saldos"
    return send_email(subject, recipients, html_content)


def send_payment_summary_email(
    recipients: list[str], context: dict[str, Any], testing: bool = False
):
    """
    Send payment summary email notification.

    Args:
        recipients: List of email addresses to notify
        context: Template context with payment summary data
        testing: Whether this is a test email
    """
    # For now, use a simple HTML template since we don't have payment templates yet
    if context.get("no_payments_needed"):
        subject = "Resumen de Pagos - Sin Pagos Requeridos"
        html_content = f"""
        <html>
        <body>
        <h2>Resumen de Pagos - {context["generation_date"]}</h2>
        <p><strong>No hay pagos de tarjetas de crédito requeridos en este momento.</strong></p>
        <p>Todas las tarjetas de crédito tienen saldo positivo o cero.</p>
        <p><em>Generado automáticamente el {context["generation_date"]}</em></p>
        </body>
        </html>
        """
    else:
        subject = f"Resumen de Pagos - {context['unique_cards']} Tarjetas Procesadas"

        instructions_html = ""
        for inst in context["instructions"][:10]:  # Limit to first 10 for email
            instructions_html += f"""
            <tr>
            <td>{inst["credit_card"]}</td>
            <td>${inst["payment_amount"]:,.2f}</td>
            <td>{inst["payment_source"]}</td>
            <td>{inst["rule_type"]}</td>
            </tr>
            """

        if len(context["instructions"]) > 10:
            instructions_html += f"""
            <tr><td colspan="4"><em>... y {len(context["instructions"]) - 10} transferencias más en Google Sheets</em></td></tr>
            """

        html_content = f"""
        <html>
        <body>
        <h2>Resumen de Pagos Generado - {context["generation_date"]}</h2>
        <h3>Resumen</h3>
        <ul>
        <li><strong>Total Deuda:</strong> ${context["total_debt"]:,.2f}</li>
        <li><strong>Total Pagos:</strong> ${context["total_payments"]:,.2f}</li>
        <li><strong>Tarjetas Procesadas:</strong> {context["unique_cards"]}</li>
        <li><strong>Pagos Parciales:</strong> {context["partial_payments"]}</li>
        </ul>
        <h3>Instrucciones de Pago (Primeras 10)</h3>
        <table border="1" style="border-collapse: collapse;">
        <tr>
        <th>Tarjeta de Crédito</th>
        <th>Monto a Transferir</th>
        <th>Cuenta de Origen</th>
        <th>Tipo de Regla</th>
        </tr>
        {instructions_html}
        </table>
        <p><strong>Consulta Google Sheets para las instrucciones completas y para marcar los pagos como procesados.</strong></p>
        <p><em>Generado automáticamente el {context["generation_date"]}</em></p>
        </body>
        </html>
        """

    if testing:
        subject = f"[TEST] {subject}"

    return send_email(subject, recipients, html_content)
