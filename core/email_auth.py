"""
=============================================================================
PROJECT LIBRA: SECURE EMAIL AUTHENTICATION & OTP DISPATCH MODULE
Target: core/email_auth.py
Role: Generates, dispatches, and logs One-Time Passcodes (OTP) for user registration
      and multi-user login. Supports Gmail/SMTP TLS dispatch and local fallback logging.
=============================================================================
"""

import os
import json
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("LibraEmailAuth")


def load_smtp_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Loads SMTP configuration from config.json if available."""
    default_cfg = {
        "enabled": False,
        "host": "smtp.gmail.com",
        "port": 587,
        "user": "",
        "password": "",
        "sender_email": "",
        "sender_name": "Project Libra Security"
    }
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    full_path = os.path.join(project_root, config_path) if not os.path.isabs(config_path) else config_path

    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                smtp_data = data.get("smtp", {})
                default_cfg.update(smtp_data)
                if not default_cfg.get("sender_email") and data.get("web_server", {}).get("admin_email"):
                    default_cfg["sender_email"] = data["web_server"]["admin_email"]
        except Exception as e:
            logger.warning(f"Failed to read SMTP config from {full_path}: {e}")

    # Merge local uncommitted secrets if config.local.json exists
    local_cfg_path = os.path.join(project_root, "config.local.json")
    if os.path.exists(local_cfg_path):
        try:
            with open(local_cfg_path, "r", encoding="utf-8") as f:
                ldata = json.load(f)
                if "smtp" in ldata:
                    default_cfg.update(ldata["smtp"])
        except Exception:
            pass

    return default_cfg


def log_verification_code_fallback(to_email: str, code: str) -> str:
    """Logs the verification code to logs/verification_codes.log for dev testing/troubleshooting."""
    import datetime
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "verification_codes.log")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] EMAIL: {to_email} | CODE: {code}\n"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.error(f"Failed to write to verification_codes.log: {e}")

    logger.info(f"[LIBRA AUTH OTP] Generated passcode {code} for {to_email}")
    return log_file


def send_verification_email(
    to_email: str,
    code: str,
    config_path: str = "config.json"
) -> Tuple[bool, str]:
    """
    Sends a 6-digit OTP email to the recipient address.
    If SMTP is configured and enabled, sends real email over TLS.
    If SMTP is not configured or encounters an error, logs code to logs/verification_codes.log.
    Returns: (success_boolean, status_message)
    """
    clean_email = to_email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        return False, "Invalid email address format."

    # Always log to local verification codes log for audit / instant dev reference
    log_file = log_verification_code_fallback(clean_email, code)

    cfg = load_smtp_config(config_path)
    enabled = cfg.get("enabled", False)
    smtp_host = cfg.get("host", "smtp.gmail.com")
    smtp_port = int(cfg.get("port", 587))
    smtp_user = cfg.get("user", "")
    smtp_pass = cfg.get("password", "")
    sender_email = cfg.get("sender_email") or smtp_user
    sender_name = cfg.get("sender_name", "Project Libra Security")

    # If SMTP is not actively configured with credentials
    if not enabled or not smtp_user or not smtp_pass:
        return (
            False,
            f"SMTP not yet configured in config.json. Passcode '{code}' has been logged to {os.path.basename(log_file)}."
        )

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your Project Libra Verification Code: {code}"
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = clean_email

    # Plain text version
    text_content = (
        f"Project Libra Security Verification\n\n"
        f"Your one-time passcode is: {code}\n\n"
        f"This code will expire in 10 minutes. Enter this code on the Project Libra web interface to log in.\n"
        f"If you did not request this code, you can safely ignore this email.\n"
    )

    import datetime
    curr_year = datetime.datetime.now().year

    # Cybernetic Dark-Mode HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Project Libra Verification</title>
  <style>
    body {{
      background-color: #0b0f19;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 40px 20px;
      color: #e2e8f0;
    }}
    .card {{
      max-width: 520px;
      margin: 0 auto;
      background: #111827;
      border: 1px solid #1e293b;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }}
    .header {{
      background: linear-gradient(135deg, #0f172a, #1e1b4b);
      padding: 30px;
      text-align: center;
      border-bottom: 1px solid #312e81;
    }}
    .header h1 {{
      margin: 0;
      font-size: 22px;
      color: #00f2fe;
      letter-spacing: 2px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .body {{
      padding: 35px 30px;
      text-align: center;
    }}
    .body p {{
      font-size: 15px;
      line-height: 1.6;
      color: #94a3b8;
      margin-top: 0;
    }}
    .code-box {{
      display: inline-block;
      margin: 25px auto;
      padding: 16px 36px;
      background: #030712;
      border: 2px solid #00f2fe;
      border-radius: 12px;
      font-size: 36px;
      font-family: 'SF Mono', Consolas, Monaco, monospace;
      font-weight: 800;
      letter-spacing: 10px;
      color: #38bdf8;
      box-shadow: 0 0 20px rgba(0, 242, 254, 0.25);
    }}
    .notice {{
      font-size: 13px;
      color: #64748b;
      margin-top: 25px;
    }}
    .footer {{
      border-top: 1px solid #1e293b;
      padding: 20px;
      text-align: center;
      font-size: 12px;
      color: #475569;
      background: #090d16;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>PROJECT LIBRA</h1>
    </div>
    <div class="body">
      <p>Use the following 6-digit authentication code to verify your identity and enter your private session:</p>
      <div class="code-box">{code}</div>
      <p class="notice">This single-use code is valid for <strong>10 minutes</strong>. Never share this code with anyone.</p>
    </div>
    <div class="footer">
      Autonomous AI Agent &copy; {curr_year} Project Libra. Hosted via Secure Cloudflare Tunnel.
    </div>
  </div>
</body>
</html>
"""

    part1 = MIMEText(text_content, "plain")
    part2 = MIMEText(html_content, "html")
    msg.attach(part1)
    msg.attach(part2)

    try:
        context = ssl.create_default_context()
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=12) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

        logger.info(f"Successfully dispatched OTP verification email to {clean_email}")
        return True, "Verification code sent to your email inbox."

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failure for {clean_email}: {e}")
        hint = (
            "Gmail requires a 16-character Google App Password (not your account login password). "
            "Please create an App Password at https://myaccount.google.com/apppasswords."
        )
        return False, f"{hint} Code '{code}' saved to {os.path.basename(log_file)}."
    except Exception as e:
        err_msg = str(e)
        logger.error(f"SMTP dispatch failure for {clean_email}: {e}")
        if "BadCredentials" in err_msg or "535" in err_msg or "Connection unexpectedly closed" in err_msg:
            hint = "Gmail requires a 16-character App Password (visit https://myaccount.google.com/apppasswords)."
            return False, f"{hint} Code '{code}' saved to {os.path.basename(log_file)}."
        return False, f"Email delivery error ({err_msg}). Code '{code}' saved to {os.path.basename(log_file)}."


# ---------------------------------------------------------------------------
# GOOGLE AUTHENTICATOR (RFC 6238 TOTP) ENGINE
# ---------------------------------------------------------------------------
import base64
import struct
import hmac
import hashlib
import time
import secrets


def generate_totp_secret() -> str:
    """Generates a random Base32 TOTP secret string for Google Authenticator (16 chars)."""
    return base64.b32encode(secrets.token_bytes(10)).decode('utf-8').replace('=', '')


def generate_totp_uri(secret_b32: str, email: str, issuer: str = "Project Libra") -> str:
    """Returns standard otpauth:// URI for Google Authenticator QR or manual setup."""
    import urllib.parse
    clean_email = urllib.parse.quote(email)
    clean_issuer = urllib.parse.quote(issuer)
    return f"otpauth://totp/{clean_issuer}:{clean_email}?secret={secret_b32}&issuer={clean_issuer}&algorithm=SHA1&digits=6&period=30"


def get_current_totp_code(secret_b32: str, intervals_no: int = None) -> str:
    """Calculates current 6-digit Google Authenticator code for a given Base32 secret."""
    if not secret_b32:
        return ""
    if intervals_no is None:
        intervals_no = int(time.time() // 30)
    try:
        pad_len = (8 - len(secret_b32) % 8) % 8
        padded = secret_b32 + ('=' * pad_len)
        key = base64.b32decode(padded, casefold=True)
        msg = struct.pack(">Q", intervals_no)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[19] & 15
        code = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
        return f"{code:06d}"
    except Exception:
        return ""


def verify_totp_code(secret_b32: str, code: str, window: int = 1) -> bool:
    """Verifies a 6-digit Google Authenticator TOTP code within a 30-second time window."""
    clean_code = str(code).strip()
    if len(clean_code) != 6 or not clean_code.isdigit() or not secret_b32:
        return False
    curr_step = int(time.time() // 30)
    for offset in range(-window, window + 1):
        if get_current_totp_code(secret_b32, curr_step + offset) == clean_code:
            return True
    return False
