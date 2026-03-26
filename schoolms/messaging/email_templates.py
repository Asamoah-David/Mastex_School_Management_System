"""
Email Templates for Mastex SchoolOS
Professional HTML email templates for various notifications
"""

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags


def send_fee_reminder_email(parent_email, parent_name, student_name, amount_due, due_date, school_name):
    """Send fee reminder email to parent."""
    subject = f"Fee Payment Reminder - {student_name} | {school_name}"
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #4F46E5, #4338CA); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .amount {{ font-size: 28px; font-weight: bold; color: #ef4444; text-align: center; margin: 20px 0; }}
            .details {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; }}
            .button {{ display: inline-block; background: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 {school_name}</h1>
                <p>Fee Payment Reminder</p>
            </div>
            <div class="content">
                <p>Dear {parent_name},</p>
                <p>This is a friendly reminder regarding unpaid school fees for your child.</p>
                
                <div class="details">
                    <p><strong>Student:</strong> {student_name}</p>
                    <p><strong>Amount Due:</strong> <span style="color: #ef4444; font-weight: bold;">{amount_due}</span></p>
                    <p><strong>Due Date:</strong> {due_date}</p>
                </div>
                
                <p>Please ensure payment is made on time to avoid any inconvenience.</p>
                
                <p style="text-align: center;">
                    <a href="#" class="button">Pay Fees Now</a>
                </p>
                
                <p>If you have already made the payment, please disregard this message.</p>
                
                <p>For any questions, please contact the school administration.</p>
                
                <p>Best regards,<br><strong>{school_name} Administration</strong></p>
            </div>
            <div class="footer">
                <p>This is an automated message from {school_name} School Management System.</p>
                <p>© {school_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[parent_email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_announcement_email(parent_emails, school_name, title, message, author_name):
    """Send announcement email to multiple recipients."""
    subject = f"📢 {title} - {school_name}"
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #4F46E5, #4338CA); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .message-box {{ background: white; padding: 20px; border-left: 4px solid #4F46E5; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📢 {school_name}</h1>
                <p>New Announcement</p>
            </div>
            <div class="content">
                <h2 style="color: #1e40af; margin-top: 0;">{title}</h2>
                <div class="message-box">
                    {message}
                </div>
                <p>Posted by: <strong>{author_name}</strong></p>
                <p>Please check the school portal for more details.</p>
            </div>
            <div class="footer">
                <p>© {school_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=parent_emails,
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_results_published_email(parent_email, parent_name, student_name, term_name, school_name):
    """Send email when results are published."""
    subject = f"📊 Results Published - {student_name} | {term_name} | {school_name}"
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #22c55e, #16a34a); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #22c55e; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 {school_name}</h1>
                <p>Results Published!</p>
            </div>
            <div class="content">
                <p>Dear {parent_name},</p>
                <p>We are pleased to inform you that the results for <strong>{term_name}</strong> have been published.</p>
                
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Student:</strong> {student_name}</p>
                    <p><strong>Term:</strong> {term_name}</p>
                </div>
                
                <p>You can now view your child's results by logging into the school portal.</p>
                
                <p style="text-align: center;">
                    <a href="#" class="button">View Results</a>
                </p>
                
                <p>If you have any questions about the results, please contact the school.</p>
            </div>
            <div class="footer">
                <p>© {school_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[parent_email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_attendance_alert_email(parent_email, parent_name, student_name, date, status, school_name):
    """Send email when student is absent or late."""
    status_text = "Absent" if status == "absent" else "Late"
    emoji = "❌" if status == "absent" else "⏰"
    color = "#ef4444" if status == "absent" else "#f59e0b"
    
    subject = f"{emoji} Attendance Alert - {student_name} | {school_name}"
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, {color}, #dc2626); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .alert {{ background: white; padding: 20px; border-radius: 8px; border-left: 4px solid {color}; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 {school_name}</h1>
                <p>Attendance Alert</p>
            </div>
            <div class="content">
                <p>Dear {parent_name},</p>
                
                <div class="alert">
                    <p style="font-size: 18px; margin: 0;"><strong>{emoji} Your child ({student_name}) was marked as {status_text} on {date}.</strong></p>
                </div>
                
                <p>We kindly request that you ensure your child attends school regularly and punctually.</p>
                
                <p>If there is a valid reason for your child's absence or lateness, please contact the school administration.</p>
                
                <p>Thank you for your cooperation.</p>
                
                <p>Best regards,<br><strong>{school_name} Administration</strong></p>
            </div>
            <div class="footer">
                <p>© {school_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[parent_email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_welcome_email(user_email, user_name, school_name, role):
    """Send welcome email to new users."""
    subject = f"Welcome to {school_name} - School Management System"
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #4F46E5, #4338CA); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
            .features {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .features li {{ margin: 10px 0; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 Welcome to {school_name}!</h1>
                <p>Your account has been created</p>
            </div>
            <div class="content">
                <p>Dear {user_name},</p>
                <p>Welcome to the {school_name} School Management System! Your account has been successfully created.</p>
                
                <div class="features">
                    <p><strong>Your Role:</strong> {role}</p>
                    <p><strong>Login URL:</strong> <a href="#">Click here to login</a></p>
                </div>
                
                <h3>Key Features:</h3>
                <ul class="features">
                    <li>📊 View academic results and progress</li>
                    <li>📅 Check attendance records</li>
                    <li>💰 View fee statements and payments</li>
                    <li>📢 Receive school announcements</li>
                    <li>📱 Get SMS notifications</li>
                </ul>
                
                <p style="text-align: center;">
                    <a href="#" class="button">Login to Portal</a>
                </p>
                
                <p>If you have any questions, please contact the school administration.</p>
                
                <p>Best regards,<br><strong>{school_name} Administration</strong></p>
            </div>
            <div class="footer">
                <p>© {school_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
