"""Sign in with phone number + one-time code. Also the profile page and sign out."""
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .models import OtpCode, User, db, utcnow
from .ratelimit import hit
from .sms import SmsNotConfigured, send_sms

bp = Blueprint("auth", __name__)

OTP_TTL = timedelta(minutes=10)
MAX_CODES_PER_HOUR = 5
MAX_ATTEMPTS = 5


def normalize_phone(raw):
    """Indian mobile numbers only for now: returns +91XXXXXXXXXX or None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if re.fullmatch(r"[6-9]\d{9}", digits) else None


def safe_next(target):
    # Only send people back to pages on this site.
    # A backslash counts as a slash in browsers, so "/\\evil.com" would leave the site too.
    ok = target and target.startswith("/") and not target.startswith("//") and "\\" not in target
    return target if ok else url_for("main.home")


@bp.app_template_global()
def event_from_next(next_url):
    """The event someone was about to book, if the sign-in link came from one."""
    from .routes import store

    m = re.match(r"^/events/([a-z0-9-]+)(/|$)", next_url or "")
    return store().get(m.group(1)) if m else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next", "")
    if g.user:
        return redirect(safe_next(next_url))
    error = None
    phone_raw = request.form.get("phone", "")
    if request.method == "POST":
        phone = normalize_phone(phone_raw)
        recent = OtpCode.query.filter(OtpCode.phone == phone, OtpCode.created_at > utcnow() - timedelta(hours=1)).count() if phone else 0
        if not phone:
            error = "Enter a 10-digit Indian mobile number."
        elif recent >= MAX_CODES_PER_HOUR or not hit("otp"):
            error = "Too many codes asked for this number. Please try again in an hour."
        else:
            code = f"{secrets.randbelow(10**6):06d}"
            try:
                send_sms(phone, f"{code} is your Eventouse sign-in code. It expires in 10 minutes. Don't share it.")
            except SmsNotConfigured:
                current_app.logger.exception("SMS not configured")
                error = "We couldn't send the code right now. Please try again shortly."
            else:
                db.session.add(OtpCode(phone=phone, code_hash=generate_password_hash(code), expires_at=utcnow() + OTP_TTL))
                db.session.commit()
                session["otp_phone"] = phone
                if current_app.config["SMS_PROVIDER"] == "console":
                    session["dev_otp"] = code  # shown on the next page in development only
                return redirect(url_for("auth.verify", next=next_url or None))
    return render_template("auth/login.html", error=error, phone=phone_raw, next=next_url)


@bp.route("/login/verify", methods=["GET", "POST"])
def verify():
    phone = session.get("otp_phone")
    next_url = request.values.get("next", "")
    if not phone:
        return redirect(url_for("auth.login", next=next_url or None))
    error = None
    if request.method == "POST":
        otp = (OtpCode.query.filter(OtpCode.phone == phone, OtpCode.used.is_(False), OtpCode.expires_at > utcnow())
               .order_by(OtpCode.created_at.desc()).first())
        code = re.sub(r"\D", "", request.form.get("code", ""))
        if otp is None:
            error = "That code expired. Ask for a new one."
        elif otp.attempts >= MAX_ATTEMPTS:
            error = "Too many wrong tries. Ask for a new code."
        elif not check_password_hash(otp.code_hash, code):
            otp.attempts += 1
            db.session.commit()
            error = "That code isn't right. Check the SMS and try again."
        else:
            otp.used = True
            user = User.query.filter_by(phone=phone).first()
            if user is None:
                user = User(phone=phone)
                db.session.add(user)
            db.session.commit()
            csrf = session.get("csrf")
            session.clear()  # new session id after sign-in
            session.update(uid=user.id, csrf=csrf)
            session.permanent = True
            if not user.name:
                return redirect(url_for("auth.account", next=next_url or None, welcome=1))
            flash(f"Welcome back, {user.first_name}!")
            return redirect(safe_next(next_url))
    return render_template("auth/verify.html", phone=phone, error=error, next=next_url,
                           dev_code=session.get("dev_otp") if current_app.config["SMS_PROVIDER"] == "console" else None)


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    next_url = request.values.get("next", "")
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        if len(name) < 2:
            error = "Please enter your name."
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            error = "That email doesn't look right."
        else:
            g.user.name, g.user.email = name[:120], email[:200]
            db.session.commit()
            flash("Profile saved.")
            return redirect(safe_next(next_url) if next_url else url_for("auth.account"))
    return render_template("auth/account.html", error=error, next=next_url, welcome=request.args.get("welcome"))


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You're signed out.")
    return redirect(url_for("main.home"))
