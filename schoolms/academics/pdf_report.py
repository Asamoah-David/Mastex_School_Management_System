"""
PDF Report Card Generator for Mastex SchoolOS
Generates professional PDF report cards for students
"""

import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from django.http import HttpResponse

logger = logging.getLogger(__name__)


def generate_report_card_pdf(student, results, attendance_data, school, term, academic_year):
    """
    Generate a PDF report card for a student.
    
    Args:
        student: Student model instance
        results: QuerySet of Result objects
        attendance_data: Dict with attendance stats
        school: School model instance
        term: Term model instance
        academic_year: String
    
    Returns:
        HttpResponse with PDF content
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=6,
        textColor=colors.HexColor('#1e40af')
    )
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=4
    )
    
    subheader_style = ParagraphStyle(
        'SubHeader',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=2
    )
    
    # School Header
    elements.append(Paragraph(f"<b>{school.name or 'School Name'}</b>", title_style))
    elements.append(Paragraph(f"{school.address or ''}", subheader_style))
    elements.append(Paragraph(f"Tel: {school.phone or ''} | Email: {school.email or ''}", subheader_style))
    elements.append(Spacer(1, 10))
    
    # Report Card Title
    elements.append(Paragraph("<b>STUDENT REPORT CARD</b>", ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=10,
        textColor=colors.HexColor('#1e40af')
    )))
    
    # Student Info Table
    student_info = [
        ['STUDENT NAME:', f"{student.user.get_full_name() or student.user.username}", 
         'ADMISSION NO:', student.admission_number],
        ['CLASS:', student.class_name or 'N/A',
         'TERM:', term.name if term else 'N/A'],
        ['ACADEMIC YEAR:', academic_year,
         'DATE:', ''],
    ]
    
    student_table = Table(student_info, colWidths=[1.8*inch, 2.8*inch, 1.8*inch, 2.8*inch])
    student_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#374151')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#374151')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 15))
    
    # Results Table
    if results:
        # Calculate totals
        total_score = sum(r.score for r in results if r.score)
        total_possible = len(results) * 100
        average = total_score / len(results) if results else 0
        
        # Results Header
        elements.append(Paragraph("<b>ACADEMIC PERFORMANCE</b>", ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=8,
            textColor=colors.HexColor('#1e40af')
        )))
        
        # Results table
        result_data = [['SUBJECT', 'SCORE', 'GRADE', 'REMARKS']]
        for r in results:
            grade = calculate_grade(r.score)
            remark = get_remark(r.score)
            result_data.append([
                r.subject.name if hasattr(r, 'subject') and r.subject else 'N/A',
                f"{r.score:.1f}" if r.score else "N/A",
                grade,
                remark
            ])
        
        # Add totals row
        result_data.append([
            'TOTAL',
            f"{total_score:.1f}",
            '',
            ''
        ])
        result_data.append([
            'AVERAGE',
            f"{average:.1f}%",
            calculate_grade(average),
            get_remark(average)
        ])
        
        result_table = Table(result_data, colWidths=[2.5*inch, 1.2*inch, 1*inch, 3.5*inch])
        result_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -3), 'Helvetica'),
            ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, -2), (-1, -1), colors.HexColor('#e5e7eb')),
            ('ALIGN', (1, 0), (2, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(result_table)
        elements.append(Spacer(1, 15))
    
    # Attendance Section
    elements.append(Paragraph("<b>ATTENDANCE RECORD</b>", ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=8,
        textColor=colors.HexColor('#1e40af')
    )))
    
    attendance_data_list = [
        ['TOTAL SCHOOL DAYS', str(attendance_data.get('total_days', 'N/A'))],
        ['DAYS PRESENT', str(attendance_data.get('present', 'N/A'))],
        ['DAYS ABSENT', str(attendance_data.get('absent', 'N/A'))],
        ['ATTENDANCE RATE', f"{attendance_data.get('percentage', 0):.1f}%"],
    ]
    
    attendance_table = Table(attendance_data_list, colWidths=[3*inch, 2*inch])
    attendance_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(attendance_table)
    elements.append(Spacer(1, 20))
    
    # Comments Section
    elements.append(Paragraph("<b>TEACHER'S COMMENTS</b>", ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=8,
        textColor=colors.HexColor('#1e40af')
    )))
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("_" * 80, styles['Normal']))
    elements.append(Paragraph("<i>Class Teacher's Signature</i>", styles['Normal']))
    
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("_" * 80, styles['Normal']))
    elements.append(Paragraph("<i>Headmaster/Headmistress Signature & Stamp</i>", styles['Normal']))
    
    # Footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(
        f"<i>Generated by Mastex SchoolOS | {timezone.now().strftime('%B %d, %Y %H:%M')}</i>",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=colors.gray)
    ))
    
    doc.build(elements)
    
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename = f"Report_Card_{student.admission_number}_{term.name if term else 'Term'}_{academic_year}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


def calculate_grade(score):
    """Calculate grade based on score."""
    if score >= 90:
        return 'A+'
    elif score >= 80:
        return 'A'
    elif score >= 70:
        return 'B+'
    elif score >= 60:
        return 'B'
    elif score >= 50:
        return 'C'
    elif score >= 40:
        return 'D'
    else:
        return 'F'


def get_remark(score):
    """Get remark based on score."""
    if score >= 90:
        return 'Excellent performance! Keep it up!'
    elif score >= 80:
        return 'Very good performance. Well done!'
    elif score >= 70:
        return 'Good performance. Continue to improve.'
    elif score >= 60:
        return 'Satisfactory. Work harder.'
    elif score >= 50:
        return 'Pass. Needs more effort.'
    elif score >= 40:
        return 'Barely passed. Seek help.'
    else:
        return 'Failed. Urgent improvement needed.'


def generate_bulk_report_cards(students, school, term, academic_year):
    """
    Generate PDF containing report cards for multiple students.
    """
    from zipfile import ZipFile
    from io import StringIO
    
    buffer = BytesIO()
    
    with ZipFile(buffer, 'w') as zip_file:
        for student in students:
            try:
                from academics.models import Result
                from operations.models import StudentAttendance
                
                results = Result.objects.filter(
                    student=student,
                    term=term
                ).select_related('subject')
                
                # Calculate attendance
                attendance_records = StudentAttendance.objects.filter(student=student)
                total_days = attendance_records.count()
                present = attendance_records.filter(status='present').count()
                absent = attendance_records.filter(status='absent').count()
                percentage = (present / total_days * 100) if total_days > 0 else 0
                
                attendance_data = {
                    'total_days': total_days,
                    'present': present,
                    'absent': absent,
                    'percentage': percentage
                }
                
                # Generate individual PDF
                pdf_buffer = BytesIO()
                doc = SimpleDocTemplate(
                    pdf_buffer,
                    pagesize=landscape(A4),
                    rightMargin=20*mm,
                    leftMargin=20*mm,
                    topMargin=15*mm,
                    bottomMargin=15*mm
                )
                
                # Add to zip
                filename = f"Report_{student.admission_number}.pdf"
                zip_file.writestr(filename, pdf_buffer.getvalue())
                
            except Exception:
                logger.warning(
                    "Error generating report card PDF for student",
                    extra={"student_id": getattr(student, "id", None)},
                    exc_info=True,
                )
                continue
    
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    filename = f"Report_Cards_{term.name if term else 'Term'}_{academic_year}.zip"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


# Import timezone for footer
from django.utils import timezone
