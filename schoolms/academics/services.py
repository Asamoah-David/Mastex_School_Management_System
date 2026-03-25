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
