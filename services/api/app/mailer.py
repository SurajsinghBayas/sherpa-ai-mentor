"""Outgoing email over SMTP (Gmail with an app password in our setup).

Templates are table-based with inline styles (what email clients actually render),
dark to match the app, and embed the Sherpa mark as an inline image (cid:) because
Gmail drops SVG and remote images may be blocked.
"""
import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .config import settings

log = logging.getLogger(__name__)

MARK_PATH = os.path.join(os.path.dirname(__file__), "assets", "sherpa-mark.png")

# brand tokens — same values as apps/web/app/globals.css (dark theme) and icon.svg
BG, CARD, BORDER = "#0d0d0d", "#141414", "#242424"
TEXT, MUTED, FAINT, ACCENT = "#ededed", "#949494", "#6b6b6b", "#5ea8ff"
SANS = "Geist,'SF Pro Text',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "'Geist Mono','SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


class MailError(RuntimeError):
    pass


def mail_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def build_message(to: str, subject: str, text: str, html_body: str) -> EmailMessage:
    """multipart/alternative (text + html), with the logo as a related inline image."""
    msg = EmailMessage()
    msg["From"] = formataddr((settings.mail_from_name, settings.smtp_user))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    mark_cid = make_msgid(domain="sherpa.ai")
    msg.add_alternative(html_body.replace("cid:sherpa-mark", "cid:" + mark_cid[1:-1]), subtype="html")
    try:
        with open(MARK_PATH, "rb") as f:
            msg.get_payload()[1].add_related(f.read(), "image", "png", cid=mark_cid,
                                             filename="sherpa.png")
    except OSError as e:  # the email still works without the logo
        log.warning("mail: logo not attached (%s)", e)
    return msg


def send_mail(to: str, subject: str, text: str, html_body: str) -> None:
    if not mail_configured():
        raise MailError("SMTP is not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD)")
    msg = build_message(to, subject, text, html_body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        log.error("mail: sending to %s failed: %s", to, e)
        raise MailError(str(e)) from e
    log.info("mail: sent to %s", to)  # never log the subject/body: they carry the code


def otp_email(code: str, purpose: str, minutes: int, to: str = "") -> tuple[str, str, str]:
    """Subject, plain text and HTML for a one-time sign-in / sign-up code."""
    signup = purpose == "signup"
    heading = "Finish creating your account" if signup else "Sign in to Sherpa AI"
    lead = (f"Enter this code on the sign-up page to verify {to or 'your email'}."
            if signup else "Enter this code on the sign-in page to continue.")
    subject = f"{code} is your Sherpa AI code"
    preheader = f"Use {code} to {'create your account' if signup else 'sign in'}. It expires in {minutes} minutes."
    text = (f"{heading}\n\n{lead}\n\n    {code}\n\n"
            f"The code expires in {minutes} minutes and works once.\n\n"
            "Didn't request this? Ignore this email. Nobody can sign in without the code.\n\n"
            "Sherpa AI · Understand any codebase, with every answer cited")
    e = html.escape
    footer_to = (f'Sent to <span style="color:{MUTED};">{e(to)}</span><br>' if to else "")
    html_body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<title>{e(subject)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@500&display=swap');
  :root {{ color-scheme: dark; supported-color-schemes: dark; }}
  @media (max-width: 480px) {{
    .card {{ padding: 28px 22px !important; }}
    .code {{ font-size: 30px !important; letter-spacing: 8px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{BG};-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{BG};">{e(preheader)}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{BG};">
  <tr><td align="center" style="padding:40px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;">

      <tr><td style="padding:0 4px 28px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="vertical-align:middle;"><img src="cid:sherpa-mark" width="28" height="28" alt="" style="display:block;border:0;border-radius:7px;"></td>
          <td style="vertical-align:middle;padding-left:10px;font-family:{SANS};font-size:16px;font-weight:600;color:{TEXT};letter-spacing:-0.2px;">Sherpa</td>
        </tr></table>
      </td></tr>

      <tr><td class="card" style="background:{CARD};border:1px solid {BORDER};border-radius:16px;padding:36px 32px;">
        <p style="margin:0 0 10px;font-family:{SANS};font-size:12px;font-weight:500;letter-spacing:1.2px;text-transform:uppercase;color:{ACCENT};">{'Verify your email' if signup else 'Sign-in code'}</p>
        <h1 style="margin:0 0 10px;font-family:{SANS};font-size:22px;line-height:30px;font-weight:600;color:{TEXT};letter-spacing:-0.3px;">{heading}</h1>
        <p style="margin:0 0 28px;font-family:{SANS};font-size:15px;line-height:24px;color:{MUTED};">{e(lead)}</p>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td align="center" style="background:{BG};border:1px solid {BORDER};border-radius:12px;padding:22px 12px;">
            <span class="code" style="font-family:{MONO};font-size:34px;line-height:40px;font-weight:500;letter-spacing:12px;color:{TEXT};padding-left:12px;">{e(code)}</span>
          </td></tr>
        </table>

        <p style="margin:16px 0 0;font-family:{SANS};font-size:13px;line-height:20px;color:{FAINT};text-align:center;">Expires in {minutes} minutes · Works once</p>

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0 0;">
          <tr><td style="border-top:1px solid {BORDER};font-size:0;line-height:0;">&nbsp;</td></tr>
        </table>
        <p style="margin:20px 0 0;font-family:{SANS};font-size:13px;line-height:20px;color:{MUTED};">Didn't request this? You can ignore this email. Nobody can sign in without the code.</p>
      </td></tr>

      <tr><td style="padding:24px 4px 0;font-family:{SANS};font-size:12px;line-height:19px;color:{FAINT};">
        {footer_to}Sherpa AI · Understand any codebase, with every answer cited
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""
    return subject, text, html_body
