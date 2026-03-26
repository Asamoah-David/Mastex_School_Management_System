"""
Advanced Operations Views - Behavior Tracker, Canteen Pre-order, Financial Reports
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Avg, Count
from datetime import timedelta

from students.models import Student
from schools.models import School
from operations.models import (
    StudentAttendance, Expense, Budget, CanteenItem, CanteenPayment,
    DisciplineIncident, BehaviorPoint
)


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
    ).select_related('student', 'student__user', 'recorded_by').order_by('-created_at')[:20]
    
    context = {
        'school': school,
        'recent_records': recent_records,
        'classes': [c for c in students.values_list('class_name', flat=True).distinct() if c],
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
            student=student,
            points=points if behavior_type == 'positive' else -abs(points),
            reason=reason,
            recorded_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Behavior points {"added" if points > 0 else "deducted"} successfully',
            'points': record.points,
            'total_points': student.behavior_points
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
    
    records = BehaviorPoint.objects.filter(student=student).select_related('recorded_by').order_by('-created_at')
    
    data = []
    for r in records:
        data.append({
            'id': r.id,
            'points': r.points,
            'reason': r.reason,
            'recorded_by': r.recorded_by.get_full_name() or r.recorded_by.username,
            'date': r.created_at.strftime('%Y-%m-%d %H:%i'),
        })
    
    return JsonResponse({
        'student': {
            'id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'total_points': student.behavior_points,
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
    
    # Get menu items
    items = CanteenItem.objects.filter(school=school, is_available=True)
    
    context = {
        'school': school,
        'menu_items': items,
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
    
    import json
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        items = data.get('items', [])  # [{item_id, quantity}]
        order_date = data.get('order_date')
        
        if not student_id or not items:
            return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)
        
        student = get_object_or_404(Student, id=student_id, school=school)
        
        total_amount = 0
        order_items = []
        
        for item_data in items:
            item = get_object_or_404(CanteenItem, id=item_data['item_id'], school=school)
            quantity = int(item_data.get('quantity', 1))
            amount = item.price * quantity
            total_amount += amount
            order_items.append({
                'item': item,
                'quantity': quantity,
                'amount': amount
            })
        
        # Create pre-order (for now, just create payment record)
        # In production, you'd have a PreOrder model
        item_list = ', '.join([f"{i['quantity']}x {i['item'].name}" for i in order_items])
        payment = CanteenPayment.objects.create(
            student=student,
            amount=total_amount,
            description=f"Pre-order for {order_date}: {item_list}",
            payment_method='prepaid'
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Pre-order placed successfully!',
            'total': total_amount,
            'order_id': payment.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== FINANCIAL REPORTS ====================

@login_required
def financial_reports_dashboard(request):
    """Dashboard showing financial reports and charts."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        messages.error(request, 'No school associated with your account.')
        return redirect('home')
    
    # Get current year
    current_year = timezone.now().year
    
    # Calculate totals
    expenses = Expense.objects.filter(school=school, expense_date__year=current_year)
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    budgets = Budget.objects.filter(school=school, academic_year=current_year)
    total_budget = budgets.aggregate(total=Sum('allocated_amount'))['total'] or 0
    
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
    
    context = {
        'school': school,
        'total_expenses': total_expenses,
        'total_budget': total_budget,
        'budget_remaining': total_budget - total_expenses,
        'expenses_by_category': list(expenses_by_category),
        'monthly_expenses': list(monthly_expenses),
        'current_year': current_year,
    }
    return render(request, 'operations/financial_reports.html', context)


@login_required
def get_financial_data(request):
    """Get financial data for charts."""
    school = getattr(request.user, 'school', None)
    if request.user.is_superuser:
        school_id = request.session.get('current_school_id')
        if school_id:
            school = get_object_or_404(School, id=school_id)
    
    if not school:
        return JsonResponse({'error': 'No school found'}, status=400)
    
    year = int(request.GET.get('year', timezone.now().year))
    
    # Get expenses
    expenses = Expense.objects.filter(school=school, expense_date__year=year)
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    # Budget data
    budgets = Budget.objects.filter(school=school, academic_year=year)
    total_budget = budgets.aggregate(total=Sum('allocated_amount'))['total'] or 0
    
    # Expenses by category
    expenses_by_category = expenses.values('category__name').annotate(
        amount=Sum('amount')
    ).order_by('-amount')
    
    # Monthly data
    from django.db.models.functions import ExtractMonth
    monthly_data = []
    for month in range(1, 13):
        month_expenses = expenses.filter(expense_date__month=month).aggregate(total=Sum('amount'))['total'] or 0
        monthly_data.append({
            'month': month,
            'expenses': month_expenses
        })
    
    return JsonResponse({
        'year': year,
        'total_expenses': total_expenses,
        'total_budget': total_budget,
        'budget_remaining': total_budget - total_expenses,
        'expenses_by_category': list(expenses_by_category),
        'monthly_data': monthly_data,
    })


# ==================== CLASS RANKINGS ====================

@login_required
def class_rankings_page(request):
    """Show class rankings based on performance."""
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
