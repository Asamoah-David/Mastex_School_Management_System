"""Staff HR: POST handlers plus payroll register (read + CSV export)."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from finance.staff_payroll_paystack import (
    initiate_staff_payroll_paystack_transfer,
    recipient_snapshot_for_route,
    school_staff_paystack_allowed,
    staff_paystack_school_owned_controls_ready,
    staff_paystack_transfers_enabled,
)

from accounts.hr_models import StaffContract, StaffPayrollPayment, StaffTeachingAssignment
from accounts.hr_utils import sync_expired_staff_contracts
from accounts.models import User
from accounts.permissions import can_manage_finance, is_school_leadership, is_super_admin, user_can_manage_school
from core.pagination import paginate
from academics.models import Subject
from students.models import SchoolClass

ALL_STAFF_ROLES = (
    "school_admin",
    "deputy_head",
    "hod",
    "teacher",
    "accountant",
    "librarian",
    "admission_officer",
    "school_nurse",
    "admin_assistant",
    "staff",
)


def _get_staff(request, pk: int) -> User:
    school = getattr(request.user, "school", None)
    qs = User.objects.filter(role__in=ALL_STAFF_ROLES)
    if school and not (request.user.is_superuser or getattr(request.user, "is_super_admin", False)):
        qs = qs.filter(school=school)
    return get_object_or_404(qs, pk=pk)


def _target_school(request, staff: User):
    return staff.school


def _require_manage(request):
    return user_can_manage_school(request.user)


def _require_leadership(request):
    return request.user.is_superuser or getattr(request.user, "is_super_admin", False) or is_school_leadership(
        request.user
    )


@login_required
def staff_hr_contract_add(request, pk: int):
    if not _require_manage(request):
        return redirect("home")
    if not _require_leadership(request):
        messages.error(request, "You do not have permission to manage contracts.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    if not school:
        messages.error(request, "Staff member has no school; cannot add a contract.")
        return redirect("accounts:staff_detail", pk=pk)
    start_raw = request.POST.get("start_date", "").strip()
    start = parse_date(start_raw) if start_raw else None
    end_raw = request.POST.get("end_date", "").strip()
    end = parse_date(end_raw) if end_raw else None
    ctype = request.POST.get("contract_type", "fixed_term").strip()
    valid_types = {c[0] for c in StaffContract.CONTRACT_TYPES}
    if ctype not in valid_types:
        ctype = "fixed_term"
    status = request.POST.get("status", "active").strip()
    valid_status = {c[0] for c in StaffContract.STATUS_CHOICES}
    if status not in valid_status:
        status = "active"
    job_title = request.POST.get("job_title", "").strip()
    notes = request.POST.get("notes", "").strip()
    if not start:
        messages.error(request, "Contract start date is required.")
        return redirect("accounts:staff_detail", pk=pk)
    StaffContract.objects.create(
        school=school,
        user=staff,
        contract_type=ctype,
        job_title=job_title,
        start_date=start,
        end_date=end,
        status=status,
        notes=notes,
    )
    messages.success(request, "Contract record added.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_hr_contract_set_status(request, pk: int, contract_id: int):
    if not _require_manage(request):
        return redirect("home")
    if not _require_leadership(request):
        messages.error(request, "You do not have permission to update contracts.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    contract = get_object_or_404(StaffContract, pk=contract_id, user=staff, school=school)
    new_status = request.POST.get("status", "").strip()
    valid_status = {c[0] for c in StaffContract.STATUS_CHOICES}
    if new_status not in valid_status:
        messages.error(request, "Invalid status.")
        return redirect("accounts:staff_detail", pk=pk)
    contract.status = new_status
    contract.save(update_fields=["status", "updated_at"])
    messages.success(request, "Contract status updated.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_hr_teaching_add(request, pk: int):
    if not _require_manage(request):
        return redirect("home")
    if not _require_leadership(request):
        messages.error(request, "You do not have permission to manage teaching assignments.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    if not school:
        messages.error(request, "Staff member has no school.")
        return redirect("accounts:staff_detail", pk=pk)
    try:
        subject_id = int(request.POST.get("subject_id", "0"))
    except ValueError:
        subject_id = 0
    subject = get_object_or_404(Subject, pk=subject_id, school=school)
    class_name = request.POST.get("class_name", "").strip()
    if not class_name:
        messages.error(request, "Class name is required.")
        return redirect("accounts:staff_detail", pk=pk)
    academic_year = request.POST.get("academic_year", "").strip()
    eff_from_raw = request.POST.get("effective_from", "").strip()
    eff_until_raw = request.POST.get("effective_until", "").strip()
    eff_from = parse_date(eff_from_raw) if eff_from_raw else None
    eff_until = parse_date(eff_until_raw) if eff_until_raw else None
    notes = request.POST.get("notes", "").strip()
    sync = request.POST.get("sync_subjects") == "on"
    StaffTeachingAssignment.objects.create(
        school=school,
        user=staff,
        subject=subject,
        class_name=class_name,
        academic_year=academic_year,
        effective_from=eff_from,
        effective_until=eff_until,
        is_active=True,
        notes=notes,
    )
    if sync:
        staff.assigned_subjects.add(subject)
    messages.success(request, f"Teaching assignment added ({subject.name} · {class_name}).")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_hr_teaching_end(request, pk: int, assignment_id: int):
    if not _require_manage(request):
        return redirect("home")
    if not _require_leadership(request):
        messages.error(request, "You do not have permission to end teaching assignments.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    row = get_object_or_404(StaffTeachingAssignment, pk=assignment_id, user=staff, school=school)
    row.is_active = False
    if not row.effective_until:
        row.effective_until = timezone.localdate()
    row.save(update_fields=["is_active", "effective_until"])
    messages.success(request, "Teaching assignment ended.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_hr_payroll_add(request, pk: int):
    if not _require_manage(request):
        return redirect("home")
    if not can_manage_finance(request.user):
        messages.error(request, "Only finance-authorised users can record payroll.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    if not school:
        messages.error(request, "Staff member has no school.")
        return redirect("accounts:staff_detail", pk=pk)
    period_label = request.POST.get("period_label", "").strip()
    paid_raw = request.POST.get("paid_on", "").strip()
    paid_on = parse_date(paid_raw) if paid_raw else None
    amount_raw = request.POST.get("amount", "").strip().replace(",", "")
    method = request.POST.get("method", "bank").strip()
    valid_methods = {c[0] for c in StaffPayrollPayment.METHOD_CHOICES}
    if method not in valid_methods:
        method = "bank"
    reference = request.POST.get("reference", "").strip()
    notes = request.POST.get("notes", "").strip()
    currency = (request.POST.get("currency") or "GHS").strip()[:8] or "GHS"
    if not period_label or not paid_on:
        messages.error(request, "Period and payment date are required.")
        return redirect("accounts:staff_detail", pk=pk)
    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, TypeError):
        messages.error(request, "Enter a valid amount.")
        return redirect("accounts:staff_detail", pk=pk)
    if amount <= 0:
        messages.error(request, "Amount must be greater than zero.")
        return redirect("accounts:staff_detail", pk=pk)
    StaffPayrollPayment.objects.create(
        school=school,
        user=staff,
        period_label=period_label,
        amount=amount,
        currency=currency,
        paid_on=paid_on,
        method=method,
        reference=reference,
        notes=notes,
        recorded_by=request.user,
    )
    messages.success(request, "Payroll payment recorded.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_assign_subjects_save(request, pk: int):
    if not _require_manage(request):
        return redirect("home")
    if not _require_leadership(request):
        messages.error(request, "You do not have permission to assign subjects.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    if not school:
        messages.error(request, "Staff member has no school.")
        return redirect("accounts:staff_detail", pk=pk)
    raw_ids = request.POST.getlist("assigned_subject_ids")
    id_list = []
    for x in raw_ids:
        try:
            id_list.append(int(x))
        except (TypeError, ValueError):
            continue
    subjects = Subject.objects.filter(school=school, pk__in=id_list)
    staff.assigned_subjects.set(subjects)
    messages.success(request, "Assigned subjects updated.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_assign_homeroom_save(request, pk: int):
    if not _require_manage(request):
        return redirect("home")
    if not _require_leadership(request):
        messages.error(request, "You do not have permission to assign a homeroom class.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    school = _target_school(request, staff)
    if not school:
        messages.error(request, "Staff member has no school.")
        return redirect("accounts:staff_detail", pk=pk)
    # Clear previous homerooms for this teacher at this school
    SchoolClass.objects.filter(school=school, class_teacher=staff).update(class_teacher=None)
    sc_raw = request.POST.get("school_class_id", "").strip()
    if sc_raw:
        try:
            sc_id = int(sc_raw)
        except ValueError:
            sc_id = None
        if sc_id:
            klass = get_object_or_404(SchoolClass, pk=sc_id, school=school)
            klass.class_teacher = staff
            klass.save(update_fields=["class_teacher"])
            messages.success(request, f"Homeroom set to {klass.name}.")
        else:
            messages.success(request, "Homeroom cleared.")
    else:
        messages.success(request, "Homeroom cleared.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_payout_profile_save(request, pk: int):
    """Save staff MoMo / bank details used for Paystack salary payouts."""
    if not _require_manage(request):
        return redirect("home")
    if not can_manage_finance(request.user):
        messages.error(request, "Only finance-authorised users can edit payout details.")
        return redirect("accounts:staff_detail", pk=pk)
    if request.method != "POST":
        return redirect("accounts:staff_detail", pk=pk)
    staff = _get_staff(request, pk)
    prev_momo = f"{staff.payroll_momo_number}|{staff.payroll_momo_network}"
    prev_bank = f"{staff.payroll_bank_account_number}|{staff.payroll_bank_code}|{staff.payroll_bank_account_name}"
    staff.payroll_momo_number = request.POST.get("payroll_momo_number", "").strip()[:15]
    staff.payroll_momo_network = request.POST.get("payroll_momo_network", "").strip()[:4]
    staff.payroll_bank_account_name = request.POST.get("payroll_bank_account_name", "").strip()[:120]
    staff.payroll_bank_account_number = request.POST.get("payroll_bank_account_number", "").strip()[:20]
    staff.payroll_bank_code = request.POST.get("payroll_bank_code", "").strip()[:12]
    new_momo = f"{staff.payroll_momo_number}|{staff.payroll_momo_network}"
    new_bank = f"{staff.payroll_bank_account_number}|{staff.payroll_bank_code}|{staff.payroll_bank_account_name}"
    if new_momo != prev_momo:
        staff.paystack_recipient_momo = ""
    if new_bank != prev_bank:
        staff.paystack_recipient_bank = ""
    staff.save(
        update_fields=[
            "payroll_momo_number",
            "payroll_momo_network",
            "payroll_bank_account_name",
            "payroll_bank_account_number",
            "payroll_bank_code",
            "paystack_recipient_momo",
            "paystack_recipient_bank",
        ]
    )
    messages.success(request, "Payout details saved. Paystack recipients will be recreated on the next transfer if needed.")
    return redirect("accounts:staff_detail", pk=pk)


@login_required
def staff_payroll_disburse(request, pk: int):
    """
    Pay a staff member through the platform: offline methods (cash, bank, MoMo record, etc.)
    or Paystack Transfer (merchant balance → staff MoMo or bank).
    """
    if not can_manage_finance(request.user):
        messages.error(request, "Only finance-authorised users can run payroll.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")
    staff = _get_staff(request, pk)
    if staff.school_id != school.pk:
        messages.error(request, "Staff member is not in your school.")
        return redirect("accounts:staff_list")

    if request.method == "GET":
        paystack_global_enabled = staff_paystack_transfers_enabled()
        paystack_school_owned_ready = staff_paystack_school_owned_controls_ready()
        return render(
            request,
            "accounts/staff_payroll_disburse.html",
            {
                "staff": staff,
                "school": school,
                "paystack_staff_enabled": school_staff_paystack_allowed(request),
                "paystack_globally_configured": paystack_global_enabled,
                "paystack_school_owned_ready": paystack_school_owned_ready,
                "paystack_currency": getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
            },
        )

    mode = request.POST.get("disbursement_mode", "").strip()
    period_label = request.POST.get("period_label", "").strip()
    paid_raw = request.POST.get("paid_on", "").strip()
    paid_on = parse_date(paid_raw) if paid_raw else None
    amount_raw = request.POST.get("amount", "").strip().replace(",", "")
    currency = (request.POST.get("currency") or "GHS").strip()[:8] or "GHS"
    notes = request.POST.get("notes", "").strip()
    reference = request.POST.get("reference", "").strip()

    method_map = {
        "offline_cash": "cash",
        "offline_bank": "bank",
        "offline_momo_record": "mobile_money",
        "offline_cheque": "cheque",
        "offline_other": "other",
        "paystack_momo": "mobile_money",
        "paystack_bank": "bank",
    }
    if mode not in method_map:
        messages.error(request, "Select how you are paying this staff member.")
        return redirect("accounts:staff_payroll_disburse", pk=pk)

    if not period_label or not paid_on:
        messages.error(request, "Period and payment date are required.")
        return redirect("accounts:staff_payroll_disburse", pk=pk)
    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, TypeError):
        messages.error(request, "Enter a valid amount.")
        return redirect("accounts:staff_payroll_disburse", pk=pk)
    if amount <= 0:
        messages.error(request, "Amount must be greater than zero.")
        return redirect("accounts:staff_payroll_disburse", pk=pk)

    method = method_map[mode]

    if mode.startswith("paystack_"):
        if not _require_leadership(request):
            messages.error(
                request,
                "Automated payouts require school leadership approval. Use record-only methods or contact a school leader.",
            )
            return redirect("accounts:staff_payroll_disburse", pk=pk)
        if not school_staff_paystack_allowed(request):
            if not staff_paystack_transfers_enabled():
                messages.error(
                    request,
                    "Paystack staff transfers are disabled. Set PAYSTACK_STAFF_TRANSFERS_ENABLED=1 and ensure PAYSTACK_SECRET_KEY is set. "
                    "Until school-owned payout controls are implemented, keep using record-only payroll methods.",
                )
            elif not staff_paystack_school_owned_controls_ready():
                messages.error(
                    request,
                    "Automated payouts are disabled until school-owned funding, reconciliation, and approval controls are fully enabled.",
                )
            else:
                messages.error(
                    request,
                    "Paystack staff payouts are turned off for your school. A platform admin can enable the "
                    "“Staff payroll (Paystack transfers)” school feature.",
                )
            return redirect("accounts:staff_payroll_disburse", pk=pk)
        route = "momo" if mode == "paystack_momo" else "bank"
        pay = StaffPayrollPayment(
            school=school,
            user=staff,
            period_label=period_label,
            amount=amount,
            currency=currency,
            paid_on=paid_on,
            method=method,
            reference=reference,
            notes=notes,
            recorded_by=request.user,
            recipient_snapshot=recipient_snapshot_for_route(staff, route)[:200],
        )
        pay.save()
        reason = f"{school.name[:40]} — {period_label}"[:110]
        ok, msg = initiate_staff_payroll_paystack_transfer(
            payment=pay,
            staff_user=staff,
            reason=reason,
            route=route,
        )
        if ok:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)
        return redirect("accounts:staff_detail", pk=pk)

    StaffPayrollPayment.objects.create(
        school=school,
        user=staff,
        period_label=period_label,
        amount=amount,
        currency=currency,
        paid_on=paid_on,
        method=method,
        reference=reference,
        notes=notes,
        recorded_by=request.user,
        paystack_status="",
        recipient_snapshot="",
    )
    messages.success(request, "Payment recorded on the platform.")
    return redirect("accounts:staff_detail", pk=pk)


def _can_see_contract_expiry(request) -> bool:
    return (
        request.user.is_superuser
        or is_super_admin(request.user)
        or is_school_leadership(request.user)
    )


@login_required
def staff_payroll_register(request):
    """
    School-wide staff salary/stipend lines (not student fees).
    Filter by paid date range; optional CSV export. Leadership sees contracts ending soon.
    """
    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to view the staff payroll register.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    sync_expired_staff_contracts(school=school)

    today = timezone.localdate()
    month_start = date(today.year, today.month, 1)
    from_raw = request.GET.get("from", "").strip()
    to_raw = request.GET.get("to", "").strip()
    date_from = parse_date(from_raw) if from_raw else month_start
    date_to = parse_date(to_raw) if to_raw else today
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    ps_filter = request.GET.get("ps", "").strip()

    qs = (
        StaffPayrollPayment.objects.filter(school=school, paid_on__gte=date_from, paid_on__lte=date_to)
        .select_related("user", "recorded_by")
        .order_by("-paid_on", "-id")
    )
    if ps_filter == "failed":
        qs = qs.filter(paystack_status="failed")
    elif ps_filter == "success":
        qs = qs.filter(paystack_status="success")
    elif ps_filter == "paystack":
        qs = qs.exclude(paystack_status="")

    failed_paystack_count = StaffPayrollPayment.objects.filter(
        school=school,
        paid_on__gte=date_from,
        paid_on__lte=date_to,
        paystack_status="failed",
    ).count()

    if request.GET.get("export") == "csv":
        sub = (school.subdomain or str(school.pk)).replace("/", "-")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="staff-payroll-{sub}-{date_from}-{date_to}.csv"'
        w = csv.writer(response)
        w.writerow(
            [
                "paid_on",
                "staff_username",
                "staff_name",
                "period_label",
                "amount",
                "currency",
                "method",
                "paystack_status",
                "paystack_transfer_code",
                "reference",
                "notes",
            ]
        )
        for p in qs.iterator():
            w.writerow(
                [
                    p.paid_on.isoformat(),
                    p.user.username,
                    p.user.get_full_name() or "",
                    p.period_label,
                    str(p.amount),
                    p.currency,
                    p.get_method_display(),
                    p.get_paystack_status_display() if p.paystack_status else "",
                    p.paystack_transfer_code,
                    p.reference,
                    (p.notes or "").replace("\n", " ")[:500],
                ]
            )
        return response

    page_obj = paginate(request, qs, per_page=40)
    totals = list(
        StaffPayrollPayment.objects.filter(school=school, paid_on__gte=date_from, paid_on__lte=date_to)
        .values("currency")
        .annotate(total=Sum("amount"), n=Count("id"))
        .order_by("currency")
    )

    expiring_contracts = []
    if _can_see_contract_expiry(request):
        horizon = today + timedelta(days=60)
        expiring_contracts = list(
            StaffContract.objects.filter(
                school=school,
                status="active",
                end_date__isnull=False,
                end_date__lte=horizon,
                end_date__gte=today,
            )
            .select_related("user")
            .order_by("end_date", "user__username")[:30]
        )

    return render(
        request,
        "accounts/staff_payroll_register.html",
        {
            "school": school,
            "date_from": date_from,
            "date_to": date_to,
            "ps_filter": ps_filter,
            "failed_paystack_count": failed_paystack_count,
            "page_obj": page_obj,
            "totals": totals,
            "expiring_contracts": expiring_contracts,
            "show_contract_expiry": _can_see_contract_expiry(request),
            "paystack_staff_enabled": school_staff_paystack_allowed(request),
        },
    )


@login_required
def staff_payroll_bulk_record(request):
    """
    Record the same payroll period for many staff at once (offline methods only).
    """
    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to record bulk payroll.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")

    staff_qs = (
        User.objects.filter(school=school, role__in=ALL_STAFF_ROLES, is_active=True)
        .select_related("school")
        .order_by("first_name", "last_name", "username")
    )

    if request.method == "POST":
        raw_ids = request.POST.getlist("staff_ids")
        period_label = request.POST.get("period_label", "").strip()
        paid_raw = request.POST.get("paid_on", "").strip()
        paid_on = parse_date(paid_raw) if paid_raw else None
        default_amount_raw = request.POST.get("default_amount", "").strip().replace(",", "")
        method = request.POST.get("method", "bank").strip()
        valid_methods = {c[0] for c in StaffPayrollPayment.METHOD_CHOICES}
        if method not in valid_methods:
            method = "bank"
        currency = (request.POST.get("currency") or "GHS").strip()[:8] or "GHS"
        notes = request.POST.get("notes", "").strip()
        reference_prefix = request.POST.get("reference_prefix", "").strip()[:80]

        if not period_label or not paid_on:
            messages.error(request, "Period label and payment date are required.")
            return redirect("accounts:staff_payroll_bulk_record")

        try:
            default_amount = Decimal(default_amount_raw)
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid default amount.")
            return redirect("accounts:staff_payroll_bulk_record")

        if default_amount <= 0:
            messages.error(request, "Default amount must be greater than zero.")
            return redirect("accounts:staff_payroll_bulk_record")

        id_set = set()
        for x in raw_ids:
            try:
                id_set.add(int(x))
            except (TypeError, ValueError):
                continue

        if not id_set:
            messages.error(request, "Select at least one staff member.")
            return redirect("accounts:staff_payroll_bulk_record")

        eligible = set(staff_qs.filter(pk__in=id_set).values_list("pk", flat=True))
        created = 0
        for uid in sorted(eligible):
            amt_raw = (request.POST.get(f"amount_{uid}", "") or "").strip().replace(",", "")
            try:
                amount = Decimal(amt_raw) if amt_raw else default_amount
            except (InvalidOperation, TypeError):
                amount = default_amount
            if amount <= 0:
                continue
            ref = f"{reference_prefix} {uid}".strip() if reference_prefix else ""
            StaffPayrollPayment.objects.create(
                school=school,
                user_id=uid,
                period_label=period_label,
                amount=amount,
                currency=currency,
                paid_on=paid_on,
                method=method,
                reference=ref[:120],
                notes=notes,
                recorded_by=request.user,
                paystack_status="",
                recipient_snapshot="",
            )
            created += 1

        if created:
            messages.success(request, f"Recorded {created} payroll line(s).")
        else:
            messages.warning(request, "No payroll lines were created. Check amounts and selections.")
        return redirect("accounts:staff_payroll_register")

    return render(
        request,
        "accounts/staff_payroll_bulk.html",
        {"school": school, "staff_list": staff_qs},
    )


@login_required
def staff_payroll_payslip(request, payment_id: int):
    pay = get_object_or_404(
        StaffPayrollPayment.objects.select_related("school", "user", "recorded_by"),
        pk=payment_id,
    )
    viewer = request.user
    allowed = False
    if viewer == pay.user:
        allowed = True
    elif can_manage_finance(viewer) and getattr(viewer, "school", None) == pay.school:
        allowed = True
    elif viewer.is_superuser or getattr(viewer, "is_super_admin", False):
        allowed = True

    if not allowed:
        return redirect("home")

    return render(
        request,
        "accounts/staff_payroll_payslip.html",
        {"payment": pay, "school": pay.school},
    )


@login_required
def staff_my_payroll(request):
    """Staff: view own payroll lines and open printable payslips."""
    if getattr(request.user, "role", None) not in ALL_STAFF_ROLES:
        return redirect("home")
    payments = (
        StaffPayrollPayment.objects.filter(user=request.user)
        .select_related("school")
        .order_by("-paid_on", "-id")[:120]
    )
    return render(
        request,
        "accounts/staff_my_payroll.html",
        {"payments": payments},
    )


@login_required
def staff_payroll_export_user(request, pk: int):
    """CSV of all payroll lines for one staff member (finance)."""
    if not can_manage_finance(request.user):
        messages.error(request, "You do not have permission to export payroll.")
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school:
        return redirect("accounts:dashboard")
    staff = _get_staff(request, pk)
    if staff.school_id != school.pk:
        return redirect("accounts:staff_list")
    sync_expired_staff_contracts(school=school)
    qs = (
        StaffPayrollPayment.objects.filter(school=school, user=staff)
        .select_related("user")
        .order_by("-paid_on", "-id")
    )
    sub = (school.subdomain or str(school.pk)).replace("/", "-")
    uname = staff.username.replace("/", "-")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="payroll-{sub}-{uname}.csv"'
    w = csv.writer(response)
    w.writerow(
        [
            "paid_on",
            "period_label",
            "amount",
            "currency",
            "method",
            "reference",
            "notes",
        ]
    )
    for p in qs.iterator():
        w.writerow(
            [
                p.paid_on.isoformat(),
                p.period_label,
                str(p.amount),
                p.currency,
                p.get_method_display(),
                p.reference,
                (p.notes or "").replace("\n", " ")[:500],
            ]
        )
    return response
