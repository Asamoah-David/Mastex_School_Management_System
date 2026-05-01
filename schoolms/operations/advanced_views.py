"""
Advanced Operations Views - Behavior Tracker, Canteen Pre-order, Financial Reports
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, Sum, Avg, Count
from datetime import timedelta

from students.models import Student
from schools.models import School
from operations.models import (
    StudentAttendance, Expense, Budget, CanteenItem, CanteenPayment,
    BusPayment, TextbookSale, HostelFee,
    DisciplineIncident, BehaviorPoint
)
from accounts.permissions import user_can_manage_school, can_manage_finance
from accounts.hr_models import StaffPayrollPayment
from accounts.hr_utils import sync_expired_staff_contracts


def _budget_vs_actual_rows(school, year: int):
    """Match budget lines to expense totals by category for the calendar year."""
    labels = {str(year)}
    if getattr(school, "academic_year", None):
        labels.add(school.academic_year)
    budgets = (
        Budget.objects.filter(school=school, academic_year__in=labels)
        .select_related("category")
        .order_by("category__name", "academic_year")
    )
    rows = []
    for b in budgets:
        ex = Expense.objects.filter(school=school, expense_date__year=year)
        if b.category_id:
            ex = ex.filter(category_id=b.category_id)
        else:
            ex = ex.filter(category__isnull=True)
        actual = ex.aggregate(total=Sum("amount"))["total"] or 0
        bud = float(b.allocated_amount)
        act = float(actual)
        rows.append(
            {
                "category": b.category.name if b.category else "Uncategorized",
                "academic_year": b.academic_year,
                "budgeted": bud,
                "actual": act,
                "variance": bud - act,
            }
        )
    return rows


def _can_access_canteen_preorder(user):
    if user.is_superuser:
        return True
    role = getattr(user, "role", None)
    if role in ("parent", "student"):
        return True
    return user_can_manage_school(user)


def _preorder_students_queryset(user, school):
    if not school:
        return Student.objects.none()
    qs = Student.objects.filter(school=school, status="active").select_related("user")
    if user.is_superuser or user_can_manage_school(user):
        return qs.order_by("class_name", "user__last_name", "user__first_name")
    role = getattr(user, "role", None)
    if role == "parent":
        return qs.filter(parent=user).order_by("user__last_name", "user__first_name")
    if role == "student":
        return qs.filter(user=user)
    return Student.objects.none()


def _user_may_preorder_for(user, student, school):
    if user.is_superuser:
        return True
    if student.school_id != school.id:
        return False
    if user_can_manage_school(user):
        return True
    if getattr(user, "role", None) == "parent" and student.parent_id == user.id:
        return True
    if getattr(user, "role", None) == "student" and student.user_id == user.id:
        return True
    return False


# ==================== BEHAVIOR TRACKER ====================

@login_required
def behavior_tracker_dashboard(request):
    """Dashboard for tracking student behavior."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get top positive and negative behavior students
    students = Student.objects.filter(school=school).select_related('user')
    
    # Get recent behavior records
    recent_records = BehaviorPoint.objects.filter(
        student__in=students
    ).select_related('student', 'student__user', 'awarded_by').order_by('-awarded_at')[:20]

    positive_count = BehaviorPoint.objects.filter(student__in=students, point_type='positive').count()
    negative_count = BehaviorPoint.objects.filter(student__in=students, point_type='negative').count()

    context = {
        'school': school,
        'recent_records': recent_records,
        'students_by_class': students,
        'classes': [c for c in students.values_list('class_name', flat=True).distinct() if c],
        'positive_count': positive_count,
        'negative_count': negative_count,
    }
    return render(request, 'operations/behavior_tracker.html', context)


@login_required
def add_behavior_points(request):
    """Add behavior points to a student."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'success': False, 'error': 'No school found'}, status=400)
    
    import json
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        points = int(data.get('points', 0))
        reason = data.get('reason', '').strip()
        behavior_type = data.get('type', 'positive')  # 'positive' or 'negative'
        
        if not student_id or not reason:
            return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)
        
        student = get_object_or_404(Student, id=student_id, school=school)
        
        # Create behavior record
        record = BehaviorPoint.objects.create(
            school=school,
            student=student,
            point_type=behavior_type if behavior_type in ('positive', 'negative') else 'positive',
            points=points if behavior_type == 'positive' else -abs(points),
            reason=reason,
            awarded_by=request.user
        )
        
        from django.db.models import Sum
        total = student.behavior_points.aggregate(total=Sum('points'))['total'] or 0
        return JsonResponse({
            'success': True,
            'message': f'Behavior points {"added" if points > 0 else "deducted"} successfully',
            'points': record.points,
            'total_points': total
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def get_student_behavior(request, student_id):
    """Get behavior history for a student."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    student = get_object_or_404(Student, id=student_id, school=school)
    
    records = BehaviorPoint.objects.filter(student=student).select_related('awarded_by').order_by('-awarded_at')
    
    data = []
    for r in records:
        data.append({
            'id': r.id,
            'points': r.points,
            'reason': r.reason,
            'recorded_by': r.awarded_by.get_full_name() if r.awarded_by else 'System',
            'date': r.awarded_at.strftime('%Y-%m-%d %H:%M') if r.awarded_at else '',
        })
    
    from django.db.models import Sum
    total = student.behavior_points.aggregate(total=Sum('points'))['total'] or 0
    return JsonResponse({
        'student': {
            'id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'total_points': total,
        },
        'records': data
    })


# ==================== CANTEEN PRE-ORDER ====================

@login_required
def canteen_preorder_page(request):
    """Page for parents to pre-order meals."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')

    if not _can_access_canteen_preorder(request.user):
        messages.error(request, 'You do not have access to canteen pre-order.')
        return redirect('home')
    
    items = CanteenItem.objects.filter(school=school, is_available=True)
    preorder_students = _preorder_students_queryset(request.user, school)
    
    context = {
        'school': school,
        'menu_items': items,
        'preorder_students': preorder_students,
    }
    return render(request, 'operations/canteen_preorder.html', context)


@login_required
def create_preorder(request):
    """Create a meal pre-order."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)
    
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'success': False, 'error': 'No school found'}, status=400)

    if not _can_access_canteen_preorder(request.user):
        return JsonResponse({'success': False, 'error': 'Not permitted'}, status=403)
    
    import json
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        items = data.get('items', [])  # [{item_id, quantity}]
        order_date = data.get('order_date') or timezone.now().date().isoformat()
        
        if not student_id or not items:
            return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)
        
        student = get_object_or_404(Student, id=student_id, school=school)
        if not _user_may_preorder_for(request.user, student, school):
            return JsonResponse({'success': False, 'error': 'Not allowed to order for this student'}, status=403)
        
        total_amount = 0
        order_items = []
        
        for item_data in items:
            raw_id = item_data.get('item_id')
            if raw_id is None:
                return JsonResponse({'success': False, 'error': 'Invalid line item'}, status=400)
            item = get_object_or_404(CanteenItem, id=raw_id, school=school, is_available=True)
            quantity = int(item_data.get('quantity', 1))
            if quantity < 1:
                return JsonResponse({'success': False, 'error': 'Invalid quantity'}, status=400)
            amount = item.price * quantity
            total_amount += amount
            order_items.append({
                'item': item,
                'quantity': quantity,
                'amount': amount
            })
        
        item_list = ', '.join([f"{i['quantity']}x {i['item'].name}" for i in order_items])
        desc = f"Pre-order for {order_date}: {item_list}"[:255]
        payment = CanteenPayment.objects.create(
            school=school,
            student=student,
            amount=total_amount,
            description=desc,
            recorded_by=request.user,
            payment_status='completed',
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Pre-order placed successfully!',
            'total': str(total_amount),
            'order_id': payment.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== FINANCIAL REPORTS ====================

@login_required
def financial_reports_dashboard(request):
    """Dashboard showing financial reports and charts."""
    if not (request.user.is_superuser or can_manage_finance(request.user)):
        messages.error(request, "You do not have permission to view financial reports.")
        return redirect("home")

    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')

    sync_expired_staff_contracts(school=school)
    
    # Get current year
    current_year = timezone.now().year
    
    # Calculate totals
    expenses = Expense.objects.filter(school=school, expense_date__year=current_year)
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0

    budget_year_q = Q(academic_year=str(current_year))
    if school.academic_year:
        budget_year_q |= Q(academic_year=school.academic_year)
    budgets = Budget.objects.filter(school=school).filter(budget_year_q)
    total_budget = budgets.aggregate(total=Sum('allocated_amount'))['total'] or 0
    budget_vs_actual = _budget_vs_actual_rows(school, current_year)
    
    # Expenses by category
    expenses_by_category = expenses.values('category__name').annotate(
        total=Sum('amount')
    ).order_by('-total')
    
    # Monthly expenses
    from django.db.models.functions import ExtractMonth
    monthly_expenses = expenses.annotate(
        month=ExtractMonth('expense_date')
    ).values('month').annotate(
        total=Sum('amount')
    ).order_by('month')

    staff_payroll_by_currency = list(
        StaffPayrollPayment.objects.filter(school=school, paid_on__year=current_year)
        .values("currency")
        .annotate(total=Sum("amount"))
        .order_by("currency")
    )
    staff_payroll_monthly = list(
        StaffPayrollPayment.objects.filter(school=school, paid_on__year=current_year)
        .annotate(month=ExtractMonth("paid_on"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    staff_payroll_monthly_max = 1.0
    for m in staff_payroll_monthly:
        t = float(m["total"] or 0)
        if t > staff_payroll_monthly_max:
            staff_payroll_monthly_max = t
    if staff_payroll_monthly_max < 1:
        staff_payroll_monthly_max = 1.0
    staff_payroll_monthly_max_int = max(1, int(round(staff_payroll_monthly_max)))

    # ── Income calculations for current year ──────────────────────────────
    from decimal import Decimal as _D
    from django.db.models.functions import ExtractMonth
    from finance.models import FeePayment

    fee_income = FeePayment.objects.filter(
        fee__school=school, status='completed', created_at__year=current_year
    ).aggregate(total=Sum('amount'))['total'] or _D('0')
    canteen_income = CanteenPayment.objects.filter(
        school=school, payment_status='completed', payment_date__year=current_year
    ).aggregate(total=Sum('amount'))['total'] or _D('0')
    bus_income = BusPayment.objects.filter(
        school=school, paid=True, payment_date__year=current_year
    ).aggregate(total=Sum('amount'))['total'] or _D('0')
    textbook_income = TextbookSale.objects.filter(
        school=school, payment_status='completed', sale_date__year=current_year
    ).aggregate(total=Sum('amount'))['total'] or _D('0')
    hostel_income = HostelFee.objects.filter(
        school=school, paid=True, payment_date__year=current_year
    ).aggregate(total=Sum('amount'))['total'] or _D('0')

    total_income = fee_income + canteen_income + bus_income + textbook_income + hostel_income
    net_position = total_income - _D(str(total_expenses))

    income_by_source = [
        {'source': 'School Fees', 'total': fee_income},
        {'source': 'Canteen', 'total': canteen_income},
        {'source': 'Bus', 'total': bus_income},
        {'source': 'Textbooks', 'total': textbook_income},
        {'source': 'Hostel', 'total': hostel_income},
    ]

    monthly_income_qs = (
        FeePayment.objects
        .filter(fee__school=school, status='completed', created_at__year=current_year)
        .annotate(month=ExtractMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    monthly_income = list(monthly_income_qs)
    monthly_income_max = max((float(m['total'] or 0) for m in monthly_income), default=1.0) or 1.0

    context = {
        'school': school,
        'total_expenses': total_expenses,
        'total_budget': total_budget,
        'budget_remaining': total_budget - total_expenses,
        'expenses_by_category': list(expenses_by_category),
        'monthly_expenses': list(monthly_expenses),
        'current_year': current_year,
        'staff_payroll_by_currency': staff_payroll_by_currency,
        'staff_payroll_monthly': staff_payroll_monthly,
        'staff_payroll_monthly_max': staff_payroll_monthly_max_int,
        'budget_vs_actual': budget_vs_actual,
        'total_income': total_income,
        'net_position': net_position,
        'income_by_source': income_by_source,
        'monthly_income': monthly_income,
        'monthly_income_max': max(1, int(round(monthly_income_max))),
    }
    return render(request, 'operations/financial_reports.html', context)


@login_required
def get_financial_data(request):
    """Get financial data for charts."""
    if not (request.user.is_superuser or can_manage_finance(request.user)):
        return JsonResponse({"error": "Forbidden"}, status=403)

    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)

    sync_expired_staff_contracts(school=school)
    
    year = int(request.GET.get('year', timezone.now().year))
    
    # Get expenses
    expenses = Expense.objects.filter(school=school, expense_date__year=year)
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    budget_year_q = Q(academic_year=str(year))
    if school.academic_year:
        budget_year_q |= Q(academic_year=school.academic_year)
    budgets = Budget.objects.filter(school=school).filter(budget_year_q)
    total_budget = budgets.aggregate(total=Sum('allocated_amount'))['total'] or 0
    budget_vs_actual = _budget_vs_actual_rows(school, year)
    
    # Expenses by category (same shape as dashboard template: category__name + total)
    expenses_by_category_rows = expenses.values("category__name").annotate(total=Sum("amount")).order_by("-total")

    # Monthly data
    monthly_data = []
    for month in range(1, 13):
        month_expenses = expenses.filter(expense_date__month=month).aggregate(total=Sum('amount'))['total'] or 0
        monthly_data.append({
            'month': month,
            'expenses': float(month_expenses)
        })

    payroll_by_currency = list(
        StaffPayrollPayment.objects.filter(school=school, paid_on__year=year)
        .values("currency")
        .annotate(total=Sum("amount"))
        .order_by("currency")
    )
    payroll_monthly = []
    for month in range(1, 13):
        pt = StaffPayrollPayment.objects.filter(school=school, paid_on__year=year, paid_on__month=month).aggregate(
            total=Sum("amount")
        )["total"] or 0
        payroll_monthly.append({"month": month, "total": float(pt)})
    
    return JsonResponse({
        'year': year,
        'total_expenses': float(total_expenses),
        'total_budget': float(total_budget),
        'budget_remaining': float(total_budget - total_expenses),
        'expenses_by_category': [
            {"category__name": r["category__name"], "total": float(r["total"] or 0)}
            for r in expenses_by_category_rows
        ],
        'monthly_data': monthly_data,
        'staff_payroll_by_currency': [
            {"currency": row["currency"], "total": float(row["total"] or 0)} for row in payroll_by_currency
        ],
        'staff_payroll_monthly': payroll_monthly,
        'budget_vs_actual': budget_vs_actual,
    })


# ==================== CLASS RANKINGS ====================

@login_required
def class_rankings_page(request):
    """Show class rankings based on performance."""
    from core.utils import can_manage

    if not request.user.is_superuser and not can_manage(request):
        messages.error(request, 'You do not have permission to view school rankings.')
        return redirect('home')

    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    from academics.models import Result, Term
    from django.db.models import Avg
    
    current_term = Term.objects.filter(school=school, is_current=True).first()
    
    # Get all students with their average scores
    students = Student.objects.filter(school=school).select_related('user')
    
    rankings = []
    for student in students:
        results = Result.objects.filter(student=student)
        if current_term:
            results = results.filter(term=current_term)
        
        avg_score = results.aggregate(avg=Avg('score'))['avg'] or 0
        
        # Count subjects taken
        subjects_taken = results.values('subject').distinct().count()
        
        # Attendance rate
        attendance_records = StudentAttendance.objects.filter(student=student)
        total_days = attendance_records.count()
        present_days = attendance_records.filter(status='present').count()
        attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
        
        # Calculate overall score (70% academics, 30% attendance)
        overall_score = (avg_score * 0.7) + (attendance_rate * 0.3)
        
        rankings.append({
            'student': student,
            'avg_score': round(avg_score, 1),
            'subjects_taken': subjects_taken,
            'attendance_rate': round(attendance_rate, 1),
            'overall_score': round(overall_score, 1),
        })
    
    # Sort by overall score
    rankings.sort(key=lambda x: x['overall_score'], reverse=True)
    
    context = {
        'school': school,
        'rankings': rankings,
        'current_term': current_term,
    }
    return render(request, 'operations/class_rankings.html', context)


# ==================== WRAPPER FUNCTIONS FOR URL PATTERNS ====================

# These wrapper functions call the correct functions from timetable_generator

@login_required
def auto_timetable_page(request):
    """Wrapper for auto timetable page."""
    from academics.timetable_generator import auto_timetable_generator
    return auto_timetable_generator(request)


def generate_timetable(request):
    """Wrapper for generate timetable."""
    from academics.timetable_generator import generate_timetable
    return generate_timetable(request)


@login_required
def auto_seating_plan_page(request):
    """Wrapper for auto seating plan page."""
    from academics.timetable_generator import auto_seating_plan
    return auto_seating_plan(request)


def generate_seating_plan(request):
    """Wrapper for generate seating plan."""
    from academics.timetable_generator import generate_seating_plan
    return generate_seating_plan(request)


@login_required
def behavior_tracker_page(request):
    """Wrapper for behavior tracker page."""
    return behavior_tracker_dashboard(request)


@login_required
def record_behavior(request):
    """Wrapper for record behavior."""
    return add_behavior_points(request)


@login_required
def student_behavior_history(request, student_id):
    """Wrapper for student behavior history."""
    return get_student_behavior(request, student_id)


@login_required
def financial_reports_page(request):
    """Wrapper for financial reports page."""
    return financial_reports_dashboard(request)


@login_required
def budget_vs_actual(request):
    """Wrapper for budget vs actual data."""
    return get_financial_data(request)


@login_required
def income_statement(request):
    """Wrapper for income statement data."""
    return get_financial_data(request)


@login_required
def expense_breakdown(request):
    """Wrapper for expense breakdown data."""
    return get_financial_data(request)
