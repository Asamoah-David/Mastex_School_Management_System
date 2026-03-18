"""
Automatic notifications for academics - sends SMS/Email when important events occur.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Homework, Result


@receiver(post_save, sender=Homework)
def homework_created_notification(sender, instance, created, **kwargs):
    """Send notification when homework is assigned."""
    if created:
        try:
            from messaging.utils import send_sms
            from accounts.models import User
            from students.models import Student
            
            school = instance.school
            
            # Get students in this class
            students = Student.objects.filter(school=school, class_name=instance.class_name).select_related('user')
            
            for student in students:
                if student.user.phone:
                    try:
                        message = f"New Homework: {instance.title} for {instance.class_name}. Due: {instance.due_date}. Subject: {instance.subject.name}"
                        send_sms(student.user.phone, message)
                    except Exception as e:
                        print(f"Failed to send SMS to {student.user.phone}: {e}")
                        
        except Exception as e:
            print(f"Homework notification error: {e}")


@receiver(post_save, sender=Result)
def result_uploaded_notification(sender, instance, created, **kwargs):
    """Send notification when results are uploaded."""
    if created:
        try:
            from messaging.utils import send_sms
            from accounts.models import User
            
            student = instance.student
            parent = student.parent
            
            if parent and parent.phone:
                try:
                    message = f"Result Update: {student.user.get_full_name()} scored {instance.score}% in {instance.subject.name} ({instance.exam_type.name})"
                    send_sms(parent.phone, message)
                except Exception as e:
                    print(f"Failed to send SMS to parent: {e}")
                    
        except Exception as e:
            print(f"Result notification error: {e}")
