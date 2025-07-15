import os
from dotenv import load_dotenv
import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import List, Dict, Any

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "templates"
)


def send_email(
    subject: str,
    recipients: List[str],
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


def send_balance_alert_email(recipients: List[str], context: Dict[str, Any]):
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("email_balance_alert.html")
    html_content = template.render(**context)
    subject = "Alerta de Diferencias de Saldos"
    return send_email(subject, recipients, html_content)
