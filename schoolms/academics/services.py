"""
Academic Services Module
========================
Contains business logic for grading calculations, GPA computation, and student rankings.
"""

from django.db.models import Avg, Sum, Count
from .models import (
    AssessmentScore, ExamScore, StudentResultSummary,
    GradingPolicy, GradePoint, Subject, Term, get_grade_for_score, get_grade_point_value
)
from students.models import Student


class GradingService:
    """
    Service class for handling all grading-related calculations.
    """
    
    @staticmethod
    def calculate_ca_score(student, subject, term):
        """
        Calculate the average Continuous Assessment (CA) score from all assessments.
        
        Args:
            student: Student instance
            subject: Subject instance
            term: Term instance
            
        Returns:
            float: Average CA score (0-100)
        """
        assessments = AssessmentScore.objects.filter(
            student=student,
            subject=subject,
            term=term
        )
        
        if assessments.exists():
            total = sum(a.normalized_score for a in assessments)
            return round(total / assessments.count(), 2)
        return 0.0
    
    @staticmethod
    def get_exam_score(student, subject, term):
        """
        Get the exam score for a student/subject/term.
        
        Args:
            student: Student instance
            subject: Subject instance
            term: Term instance
            
        Returns:
            float: Exam score (0-100) or 0 if not found
        """
        exam = ExamScore.objects.filter(
            student=student,
            subject=subject,
            term=term
        ).first()
        
        if exam:
            return exam.normalized_score
        return 0.0
    
    @staticmethod
    def calculate_final_score(student, subject, term, policy=None):
        """
        Calculate the final score using the school's grading policy.
        
        Formula: Final = (CA × CA_Weight) + (Exam × Exam_Weight)
        
        Args:
            student: Student instance
            subject: Subject instance
            term: Term instance
            policy: Optional GradingPolicy instance
            
        Returns:
            float: Final weighted score (0-100)
        """
        school = student.school
        
        if policy is None:
            policy = GradingPolicy.get_active_policy(school)
        
        ca_score = GradingService.calculate_ca_score(student, subject, term)
        exam_score = GradingService.get_exam_score(student, subject, term)
        
        ca_weight = policy.ca_weight / 100
        exam_weight = policy.exam_weight / 100
        
        final = (ca_score * ca_weight) + (exam_score * exam_weight)
        return round(final, 2)
    
    @staticmethod
    def get_grade_and_point(student, score, scale='5.0'):
        """
        Get the grade and grade point for a score.
        
        Args:
            student: Student instance
            score: Score value (0-100)
            scale: GPA scale ('5.0' or '4.0')
            
        Returns:
            tuple: (grade, grade_point)
        """
        school = student.school
        grade = get_grade_for_score(school, score)
        grade_point = get_grade_point_value(school, score, scale)
        return grade, grade_point
    
    @staticmethod
    def calculate_term_gpa(student, term, scale='5.0'):
        """
        Calculate the Grade Point Average (GPA) for a term.
        
        Formula: GPA = Sum(Grade Points) / Number of Subjects
        
        Args:
            student: Student instance
            term: Term instance
            scale: GPA scale
            
        Returns:
            float: GPA value
        """
        summaries = StudentResultSummary.objects.filter(
            student=student,
            term=term
        )
        
        if not summaries.exists():
            return 0.0
        
        total_points = sum(s.grade_point for s in summaries if s.grade_point > 0)
        subject_count = summaries.filter(grade_point__gt=0).count()
        
        if subject_count == 0:
            return 0.0
        
        return round(total_points / subject_count, 2)
    
    @staticmethod
    def calculate_cumulative_gpa(student, scale='5.0'):
        """
        Calculate the cumulative GPA across all terms.
        
        Args:
            student: Student instance
            scale: GPA scale
            
        Returns:
            float: Cumulative GPA
        """
        summaries = StudentResultSummary.objects.filter(student=student)
        
        if not summaries.exists():
            return 0.0
        
        total_points = sum(s.grade_point for s in summaries if s.grade_point > 0)
        subject_count = summaries.filter(grade_point__gt=0).count()
        
        if subject_count == 0:
            return 0.0
        
        return round(total_points / subject_count, 2)
    
    @staticmethod
    def calculate_class_rankings(class_name, term, school):
        """
        Calculate student rankings within a class for a specific term.
        
        Rankings are based on total final scores.
        
        Args:
            class_name: Class name string
            term: Term instance
            school: School instance
            
        Returns:
            dict: {student_id: position}
        """
        # Get all students in the class
        students = Student.objects.filter(school=school, class_name=class_name)
        
        # Calculate total scores for each student
        rankings = []
        for student in students:
            summaries = StudentResultSummary.objects.filter(
                student=student,
                term=term
            )
            
            if summaries.exists():
                total_score = sum(s.final_score for s in summaries)
                subject_count = summaries.count()
                avg_score = total_score / subject_count if subject_count > 0 else 0
                
                rankings.append({
                    'student': student,
                    'total_score': total_score,
                    'avg_score': avg_score,
                    'subject_count': subject_count
                })
        
        # Sort by average score (highest first)
        rankings.sort(key=lambda x: x['avg_score'], reverse=True)
        
        # Assign positions
        result = {}
        for i, r in enumerate(rankings, 1):
            result[r['student'].id] = i
        
        return result
    
    @staticmethod
    def calculate_cumulative_rankings(class_name, school):
        """
        Calculate cumulative student rankings across all terms.
        
        Args:
            class_name: Class name string
            school: School instance
            
        Returns:
            dict: {student_id: cumulative_position}
        """
        students = Student.objects.filter(school=school, class_name=class_name)
        
        rankings = []
        for student in students:
            summaries = StudentResultSummary.objects.filter(student=student)
            
            if summaries.exists():
                total_score = sum(s.final_score for s in summaries)
                subject_count = summaries.count()
                avg_score = total_score / subject_count if subject_count > 0 else 0
                
                rankings.append({
                    'student': student,
                    'total_score': total_score,
                    'avg_score': avg_score,
                    'subject_count': subject_count
                })
        
        rankings.sort(key=lambda x: x['avg_score'], reverse=True)
        
        result = {}
        for i, r in enumerate(rankings, 1):
            result[r['student'].id] = i
        
        return result
    
    @staticmethod
    def update_student_result_summary(student, subject, term):
        """
        Update or create the result summary for a student/subject/term.
        
        This is the main method to recalculate and store all computed values.
        
        Args:
            student: Student instance
            subject: Subject instance
            term: Term instance
            
        Returns:
            StudentResultSummary: Updated or created summary
        """
        school = student.school
        policy = GradingPolicy.get_active_policy(school)
        
        # Calculate scores
        ca_score = GradingService.calculate_ca_score(student, subject, term)
        exam_score = GradingService.get_exam_score(student, subject, term)
        final_score = GradingService.calculate_final_score(student, subject, term, policy)
        
        # Get grade and point
        grade, grade_point = GradingService.get_grade_and_point(student, final_score)
        
        # Calculate term GPA
        gpa = GradingService.calculate_term_gpa(student, term)
        
        # Create or update summary
        summary, created = StudentResultSummary.objects.update_or_create(
            student=student,
            subject=subject,
            term=term,
            defaults={
                'ca_score': ca_score,
                'exam_score': exam_score,
                'final_score': final_score,
                'grade': grade,
                'grade_point': grade_point,
                'gpa': gpa,
            }
        )
        
        # Update rankings
        GradingService.update_rankings(student, term)
        
        return summary
    
    @staticmethod
    def update_rankings(student, term):
        """
        Update term and cumulative rankings for a student.
        
        Args:
            student: Student instance
            term: Term instance
        """
        class_name = student.class_name
        school = student.school
        
        if not class_name:
            return
        
        # Update term rankings
        term_rankings = GradingService.calculate_class_rankings(class_name, term, school)
        summaries = StudentResultSummary.objects.filter(student=student, term=term)
        
        for summary in summaries:
            summary.term_position = term_rankings.get(student.id)
            summary.save(update_fields=['term_position'])
        
        # Update cumulative rankings
        cumulative_rankings = GradingService.calculate_cumulative_rankings(class_name, school)
        all_summaries = StudentResultSummary.objects.filter(student=student)
        
        cumulative_gpa = GradingService.calculate_cumulative_gpa(student)
        
        for summary in all_summaries:
            summary.cumulative_position = cumulative_rankings.get(student.id)
            summary.cumulative_gpa = cumulative_gpa
            summary.save(update_fields=['cumulative_position', 'cumulative_gpa'])
    
    @staticmethod
    def get_report_card_data(student, term=None):
        """
        Get comprehensive report card data for a student.
        
        Args:
            student: Student instance
            term: Optional Term instance (if None, gets all terms)
            
        Returns:
            dict: Report card data including results, GPA, positions
        """
        school = student.school
        policy = GradingPolicy.get_active_policy(school)
        
        # Get summaries
        summaries_qs = StudentResultSummary.objects.filter(student=student)
        if term:
            summaries_qs = summaries_qs.filter(term=term)
        
        summaries = list(summaries_qs.select_related('subject', 'term').order_by('term', 'subject'))
        
        if not summaries:
            return {
                'student': student,
                'results': [],
                'term_gpa': 0.0,
                'cumulative_gpa': 0.0,
                'term_position': None,
                'cumulative_position': None,
                'policy': policy,
            }
        
        # Calculate overall stats
        term_gpa = GradingService.calculate_term_gpa(student, term) if term else 0
        cumulative_gpa = GradingService.calculate_cumulative_gpa(student)
        
        # Get positions
        term_position = None
        cumulative_position = None
        
        if term and student.class_name:
            term_rankings = GradingService.calculate_class_rankings(
                student.class_name, term, school
            )
            term_position = term_rankings.get(student.id)
        
        if student.class_name:
            cumulative_rankings = GradingService.calculate_cumulative_rankings(
                student.class_name, school
            )
            cumulative_position = cumulative_rankings.get(student.id)
        
        return {
            'student': student,
            'results': summaries,
            'term_gpa': term_gpa,
            'cumulative_gpa': cumulative_gpa,
            'term_position': term_position,
            'cumulative_position': cumulative_position,
            'policy': policy,
        }


class SchemeBasedGradingService:
    """Compute report-card scores using an AssessmentScheme.

    Formula (matches spec exactly):
        CA  contribution  = (ca_raw  / ca_possible)  * ca_weight
        Exam contribution = (exam_raw / exam_possible) * exam_weight
        Final             = CA contribution + Exam contribution
    """

    @staticmethod
    def _raw_score_for_item(item, student):
        """Return (raw_score, is_found) for a single AssessmentSchemeItem."""
        from .models import AssessmentScore, ManualExamScore, ManualExamStudentScore
        st = item.source_type

        if st in ("quiz",):
            from .models import QuizAttempt
            if item.source_id:
                attempt = (
                    QuizAttempt.objects
                    .filter(quiz_id=item.source_id, student=student, is_completed=True)
                    .order_by("-score")
                    .first()
                )
                if attempt and attempt.score is not None:
                    # QuizAttempt.score is a percentage (0–100); scale to item.max_score
                    raw = round(float(attempt.score) / 100.0 * item.max_score, 2)
                    return raw, True
            return 0.0, False

        if st in ("online_exam",):
            try:
                from operations.models import ExamAttempt
                if item.source_id:
                    attempt = (
                        ExamAttempt.objects
                        .filter(exam_id=item.source_id, student=student, is_completed=True)
                        .order_by("-score")
                        .first()
                    )
                    if attempt and attempt.score is not None:
                        pct = float(attempt.score)
                        return round(pct / 100 * item.max_score, 2), True
            except ImportError:
                pass
            return 0.0, False

        if st in ("omr_exam",):
            from omr.models import OmrResult
            if item.source_id:
                result = OmrResult.objects.filter(exam_id=item.source_id, student=student).first()
                if result:
                    return result.score, True
            return 0.0, False

        if st in ("omr_combined",):
            from omr.models import OmrExamSectionB
            if item.source_id:
                sec_b = OmrExamSectionB.objects.filter(exam_id=item.source_id, student=student).first()
                if sec_b:
                    return sec_b.total_raw_score, True
            return 0.0, False

        if st == "manual_exam":
            if item.source_id:
                entry = ManualExamStudentScore.objects.filter(
                    exam_id=item.source_id, student=student
                ).first()
                if entry:
                    return entry.score, True
            return 0.0, False

        if st == "imported_exam":
            # Imported exam scores are read from StudentResultSummary.exam_score
            # (pre-existing result data, e.g. migrated from another system).
            # source_id is not used — there is one summary per student/subject/term.
            from .models import StudentResultSummary
            summary = StudentResultSummary.objects.filter(
                student=student, subject=item.scheme.subject, term=item.scheme.term
            ).first()
            if summary and summary.exam_score is not None:
                return float(summary.exam_score), True
            return 0.0, False

        if st in ("manual_ca", "assignment", "class_test", "other_ca"):
            qs = AssessmentScore.objects.filter(
                student=student, subject=item.scheme.subject, term=item.scheme.term
            )
            if item.source_id:
                # source_id = AssessmentType PK — filter to that specific type only
                qs = qs.filter(assessment_type_id=item.source_id)
            total = sum(float(s.score) for s in qs)
            return total, bool(qs.exists())

        return 0.0, False

    @staticmethod
    def compute_and_save(scheme, student):
        """Calculate CA + Exam contributions and upsert StudentReportCardScore."""
        from .models import StudentReportCardScore

        ca_items = [i for i in scheme.items.filter(include_in_report_card=True, category="ca")]
        exam_items = [i for i in scheme.items.filter(include_in_report_card=True, category="exam")]

        ca_raw = 0.0
        ca_possible = sum(float(i.max_score) for i in ca_items)
        ca_found_any = False
        for item in ca_items:
            raw, found = SchemeBasedGradingService._raw_score_for_item(item, student)
            ca_raw += raw
            if found:
                ca_found_any = True

        exam_raw = 0.0
        exam_possible = sum(float(i.max_score) for i in exam_items)
        exam_found_any = False
        for item in exam_items:
            raw, found = SchemeBasedGradingService._raw_score_for_item(item, student)
            exam_raw += raw
            if found:
                exam_found_any = True

        ca_contribution = round((ca_raw / ca_possible) * scheme.ca_weight, 2) if ca_possible > 0 else 0.0
        exam_contribution = round((exam_raw / exam_possible) * scheme.exam_weight, 2) if exam_possible > 0 else 0.0
        final = round(ca_contribution + exam_contribution, 2)

        has_ca_items = bool(ca_items)
        has_exam_items = bool(exam_items)
        if (has_ca_items and not ca_found_any) or (has_exam_items and not exam_found_any):
            status = "incomplete"
        elif not has_ca_items and not has_exam_items:
            status = "pending"
        else:
            status = "complete"

        obj, _ = StudentReportCardScore.objects.update_or_create(
            student=student,
            subject=scheme.subject,
            term=scheme.term,
            defaults={
                "school": scheme.school,  # use scheme.school — student.school may be None
                "scheme": scheme,
                "ca_raw_score": round(ca_raw, 2),
                "ca_total_possible": ca_possible,
                "ca_contribution": ca_contribution,
                "exam_raw_score": round(exam_raw, 2),
                "exam_total_possible": exam_possible,
                "exam_contribution": exam_contribution,
                "final_score": final,
                "status": status,
            },
        )
        return obj

    @staticmethod
    def compute_for_class(scheme):
        """Compute StudentReportCardScore for every student in scheme.class_name."""
        from django.db import transaction
        from students.models import Student
        students = list(Student.objects.filter(school=scheme.school, class_name=scheme.class_name))
        results = []
        with transaction.atomic():
            for student in students:
                results.append(SchemeBasedGradingService.compute_and_save(scheme, student))
        return results


def ensure_default_grading_setup(school):
    """
    Ensure a school has default grading configuration.
    Creates default assessment types, grading policy, and grade points.
    
    Args:
        school: School instance
    """
    from .models import AssessmentType, GradeBoundary
    
    # Create default assessment types
    default_assessment_types = [
        ('Class Exercise', 'In-class activities and pop quizzes'),
        ('Assignment', 'Homework and take-home assignments'),
        ('Project', 'Group or individual projects'),
        ('Quiz', 'Short quizzes and tests'),
        ('Homework', 'Daily homework submissions'),
    ]
    
    for name, desc in default_assessment_types:
        AssessmentType.objects.get_or_create(
            school=school,
            name=name,
            defaults={'description': desc}
        )
    
    # Create default grading policy (50/50)
    GradingPolicy.objects.get_or_create(
        school=school,
        is_default=True,
        defaults={'name': 'Default Policy', 'ca_weight': 50.0, 'exam_weight': 50.0}
    )
    
    # Create default grade points (5.0 scale)
    default_grade_points = [
        ('A+', 90, 100, 5.0),
        ('A', 80, 89, 5.0),
        ('B+', 75, 79, 4.0),
        ('B', 70, 74, 4.0),
        ('C+', 65, 69, 3.0),
        ('C', 60, 64, 3.0),
        ('D', 50, 59, 2.0),
        ('F', 0, 49, 0.0),
    ]
    
    for grade, min_s, max_s, point in default_grade_points:
        GradePoint.objects.get_or_create(
            school=school,
            grade=grade,
            scale='5.0',
            defaults={
                'min_score': min_s,
                'max_score': max_s,
                'point_value': point,
                'is_default': True
            }
        )
    
    # Create default grade boundaries for backward compatibility
    default_boundaries = [
        ('A', 80, 100),
        ('B', 70, 79),
        ('C', 60, 69),
        ('D', 50, 59),
        ('F', 0, 49),
    ]
    
    for grade, min_s, max_s in default_boundaries:
        GradeBoundary.objects.get_or_create(
            school=school,
            grade=grade,
            defaults={'min_score': min_s, 'max_score': max_s}
        )
