"""
Two-Factor Authentication views (Fix #31).

URL endpoints (add to accounts/urls.py):
    path("2fa/setup/",    totp_views.setup_2fa,    name="2fa_setup"),
    path("2fa/verify/",   totp_views.verify_2fa,   name="2fa_verify"),
    path("2fa/disable/",  totp_views.disable_2fa_view, name="2fa_disable"),
    path("2fa/challenge/",totp_views.login_challenge,  name="2fa_challenge"),
    path("2fa/backup/",   totp_views.use_backup_code,  name="2fa_backup"),
"""

import io

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts import totp_service


SESSION_KEY_2FA_USER = "_2fa_pending_user_pk"
SESSION_KEY_2FA_TS = "_2fa_pending_ts"
SESSION_KEY_2FA_SECRET = "_2fa_setup_secret"
_2FA_CHALLENGE_TTL_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Setup — generate secret + QR code
# ---------------------------------------------------------------------------

@login_required
def setup_2fa(request):
    """Step 1: Show QR code for the user to scan with their authenticator app."""
    user = request.user

    if user.totp_enabled:
        messages.info(request, "Two-factor authentication is already enabled.")
        return redirect("accounts:2fa_disable")

    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        secret = request.session.get(SESSION_KEY_2FA_SECRET)
        if not secret:
            messages.error(request, "Session expired. Please start again.")
            return redirect("accounts:2fa_setup")

        ok, backup_codes = totp_service.verify_setup(user, token, secret)
        if ok:
            del request.session[SESSION_KEY_2FA_SECRET]
            messages.success(request, "Two-factor authentication enabled. Save your backup codes now!")
            return render(request, "accounts/2fa_backup_codes.html", {"backup_codes": backup_codes})
        else:
            messages.error(request, "Invalid code. Please check your authenticator app and try again.")

    secret = totp_service.generate_secret()
    request.session[SESSION_KEY_2FA_SECRET] = secret
    uri = totp_service.get_totp_uri(user, secret)

    qr_svg = _qr_svg(uri)
    return render(request, "accounts/2fa_setup.html", {
        "secret": secret,
        "qr_svg": qr_svg,
    })


# ---------------------------------------------------------------------------
# Disable 2FA
# ---------------------------------------------------------------------------

@login_required
@require_POST
def disable_2fa_view(request):
    """Disable 2FA after the user confirms with their current password."""
    user = request.user
    password = request.POST.get("password", "")
    if not user.check_password(password):
        messages.error(request, "Incorrect password. 2FA was not disabled.")
        return redirect("accounts:profile")

    totp_service.disable_2fa(user)
    messages.success(request, "Two-factor authentication has been disabled.")
    return redirect("accounts:profile")


# ---------------------------------------------------------------------------
# Login challenge — shown after password check when 2FA is active
# ---------------------------------------------------------------------------

def login_challenge(request):
    """Step 2 of login: verify TOTP token when user has 2FA enabled."""
    import time as _time
    pending_pk = request.session.get(SESSION_KEY_2FA_USER)
    pending_ts = request.session.get(SESSION_KEY_2FA_TS, 0)
    if not pending_pk or (_time.time() - pending_ts) > _2FA_CHALLENGE_TTL_SECONDS:
        request.session.pop(SESSION_KEY_2FA_USER, None)
        request.session.pop(SESSION_KEY_2FA_TS, None)
        return redirect("login")

    if request.method == "POST":
        from django.contrib.auth import get_user_model
        User = get_user_model()
        token = request.POST.get("token", "").strip()
        try:
            user = User.objects.get(pk=pending_pk)
        except User.DoesNotExist:
            del request.session[SESSION_KEY_2FA_USER]
            return redirect("login")

        if totp_service.verify_token(user, token):
            del request.session[SESSION_KEY_2FA_USER]
            auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(request.POST.get("next", "/"))
        else:
            messages.error(request, "Invalid code. Try again or use a backup code.")

    return render(request, "accounts/2fa_challenge.html", {
        "next": request.GET.get("next", "/"),
    })


# ---------------------------------------------------------------------------
# Backup code fallback
# ---------------------------------------------------------------------------

def use_backup_code(request):
    """Allow login using a one-time backup code when TOTP is unavailable."""
    import time as _time
    pending_pk = request.session.get(SESSION_KEY_2FA_USER)
    pending_ts = request.session.get(SESSION_KEY_2FA_TS, 0)
    if not pending_pk or (_time.time() - pending_ts) > _2FA_CHALLENGE_TTL_SECONDS:
        request.session.pop(SESSION_KEY_2FA_USER, None)
        request.session.pop(SESSION_KEY_2FA_TS, None)
        return redirect("login")

    if request.method == "POST":
        from django.contrib.auth import get_user_model
        User = get_user_model()
        code = request.POST.get("code", "").strip()
        try:
            user = User.objects.get(pk=pending_pk)
        except User.DoesNotExist:
            del request.session[SESSION_KEY_2FA_USER]
            return redirect("login")

        if totp_service.verify_backup_code(user, code):
            del request.session[SESSION_KEY_2FA_USER]
            auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.warning(request, f"Backup code used. {user.totp_backup_codes.count(chr(10))+1 if user.totp_backup_codes else 0} code(s) remaining.")
            return redirect(request.POST.get("next", "/"))
        else:
            messages.error(request, "Invalid or already-used backup code.")

    return render(request, "accounts/2fa_backup.html", {
        "next": request.GET.get("next", "/"),
    })


# ---------------------------------------------------------------------------
# Internal helper — generate inline SVG QR code without saving to disk
# ---------------------------------------------------------------------------

def _qr_svg(uri: str) -> str:
    """Return an inline SVG QR code string, or empty string if qrcode unavailable."""
    try:
        import qrcode
        import qrcode.image.svg as svg_image

        factory = svg_image.SvgPathImage
        img = qrcode.make(uri, image_factory=factory, box_size=10)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")
    except Exception:
        return ""
