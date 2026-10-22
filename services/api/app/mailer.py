"""Outgoing email over SMTP (Gmail with an app password in our setup).

Templates are table-based with inline styles (what email clients actually render),
in the app's paper-and-navy brand, and embed the logo and Sherpa himself as inline
images (cid:) because Gmail drops SVG and remote images may be blocked.
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

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
MARK_PATH = os.path.join(ASSETS, "sherpa-mark.png")
# cid name -> (file, subtype); only the ones a template references are attached
INLINE = {
    "sherpa-mark": ("sherpa-mark.png", "png"),     # the app icon (apps/web/app/icon.svg)
    "sherpa-happy": ("sherpa-happy.gif", "gif"),   # mascot poses from apps/web/public/mascot
    "sherpa-guide": ("sherpa-guide.gif", "gif"),
}

# brand tokens: same values as apps/web/app/globals.css (light theme) and tailwind.config.ts
PAPER, CARD, BORDER = "#F8F5F0", "#FFFFFF", "#E3DCD0"
NAVY, NAVY_DEEP, MUTED, FAINT = "#17223D", "#101827", "#5D667A", "#8A90A0"
BLUE, SKY, CREAM, TAN = "#2F80ED", "#A9D5FF", "#FFF5E7", "#F2A65A"
SANS = "Geist,'SF Pro Text',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "'Geist Mono','SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


class MailError(RuntimeError):
    pass


def mail_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def build_message(to: str, subject: str, text: str, html_body: str) -> EmailMessage:
    """multipart/alternative (text + html), with the images as related inline parts."""
    msg = EmailMessage()
    msg["From"] = formataddr((settings.mail_from_name, settings.smtp_user))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    used = {name: make_msgid(domain="sherpa.ai") for name in INLINE if f"cid:{name}\"" in html_body}
    for name, cid in used.items():
        html_body = html_body.replace(f"cid:{name}\"", f"cid:{cid[1:-1]}\"")
    msg.add_alternative(html_body, subtype="html")
    for name, cid in used.items():
        file, subtype = INLINE[name]
        try:
            with open(os.path.join(ASSETS, file), "rb") as f:
                msg.get_payload()[1].add_related(f.read(), "image", subtype, cid=cid, filename=file)
        except OSError as e:  # the email still works without its pictures
            log.warning("mail: %s not attached (%s)", file, e)
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
    # Sherpa's line, as on the sign-in page's navy card
    says = ("Hi! I'm Sherpa. Verify your email and I'll show you around your first repository."
            if signup else "Good to see you again. Your repositories are right where you left them.")
    pose = "sherpa-guide" if signup else "sherpa-happy"
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
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{e(subject)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@500&display=swap');
  :root {{ color-scheme: light; supported-color-schemes: light; }}
  img {{ image-rendering: pixelated; }}
  @media (max-width: 480px) {{
    .pad {{ padding-left: 22px !important; padding-right: 22px !important; }}
    .code {{ font-size: 30px !important; letter-spacing: 8px !important; }}
    .guy {{ width: 88px !important; height: 88px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{PAPER};-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{PAPER};">{e(preheader)}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAPER};">
  <tr><td align="center" style="padding:36px 16px 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;">

      <!-- wordmark -->
      <tr><td style="padding:0 4px 22px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="vertical-align:middle;"><img src="cid:sherpa-mark" width="30" height="30" alt="" style="display:block;border:0;border-radius:7px;"></td>
          <td style="vertical-align:middle;padding-left:10px;font-family:{SANS};font-size:16px;font-weight:600;color:{NAVY};letter-spacing:-0.2px;">Sherpa <span style="color:{BLUE};">AI</span></td>
        </tr></table>
      </td></tr>

      <tr><td style="background:{CARD};border:1px solid {BORDER};border-radius:16px;overflow:hidden;">

        <!-- Sherpa on the navy card -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td class="pad" style="background:{NAVY};border-radius:15px 15px 0 0;padding:26px 32px 0;">
            <p style="margin:0 0 14px;font-family:{MONO};font-size:11px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:{SKY};">Sherpa AI · Codebase mentor</p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
              <td width="112" style="vertical-align:bottom;"><img class="guy" src="cid:{pose}" width="112" height="112" alt="Sherpa, the guide" style="display:block;border:0;"></td>
              <td style="vertical-align:middle;padding:0 0 24px 14px;">
                <div style="background:#26314B;border:1px solid #34405C;border-radius:10px;padding:12px 14px;font-family:{SANS};font-size:14px;line-height:21px;color:{CREAM};">{e(says)}</div>
              </td>
            </tr></table>
          </td></tr>
        </table>

        <!-- the code -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td class="pad" style="padding:30px 32px 32px;">
            <p style="margin:0 0 8px;font-family:{MONO};font-size:11px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:{BLUE};">{'Verify your email' if signup else 'Sign-in code'}</p>
            <h1 style="margin:0 0 8px;font-family:{SANS};font-size:22px;line-height:30px;font-weight:600;color:{NAVY};letter-spacing:-0.3px;">{heading}</h1>
            <p style="margin:0 0 24px;font-family:{SANS};font-size:15px;line-height:24px;color:{MUTED};">{e(lead)}</p>

            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td align="center" style="background:{CREAM};border:1px solid {BORDER};border-radius:12px;padding:22px 12px;">
                <span class="code" style="font-family:{MONO};font-size:34px;line-height:40px;font-weight:500;letter-spacing:12px;color:{NAVY};padding-left:12px;">{e(code)}</span>
              </td></tr>
            </table>

            <p style="margin:14px 0 0;font-family:{SANS};font-size:13px;line-height:20px;color:{FAINT};text-align:center;">Expires in {minutes} minutes · Works once</p>

            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:26px 0 0;">
              <tr><td style="border-top:1px solid {BORDER};font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
            <p style="margin:18px 0 0;font-family:{SANS};font-size:13px;line-height:20px;color:{MUTED};">Didn't request this? You can ignore this email. Nobody can sign in without the code.</p>
          </td></tr>
        </table>

      </td></tr>

      <!-- footer -->
      <tr><td style="padding:22px 4px 0;font-family:{SANS};font-size:12px;line-height:19px;color:{FAINT};">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 10px;"><tr>
          {''.join(f'<td style="padding-right:14px;font-family:{SANS};font-size:12px;color:{MUTED};"><span style="display:inline-block;width:6px;height:6px;background:{TAN};vertical-align:middle;margin-right:6px;"></span>{t}</td>' for t in ("Cited answers", "Architecture maps", "Guided tours"))}
        </tr></table>
        {footer_to}Sherpa AI · Understand any codebase, with every answer cited
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""
    return subject, text, html_body
