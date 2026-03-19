"""
School-scoped operations: attendance, canteen, bus, textbooks.
Each school manages these independently.
"""
from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class TeacherAttendance(models.Model):
    STATUS_CHOICES = (("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused"))
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="present")
    notes = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marked_teacher_attendances")

    class Meta:
        unique_together = ("teacher", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.date} ({self.status})"


class AcademicCalendar(models.Model):
    EVENT_TYPES = (
        ('term_start', 'Term Start'),
        ('term_end', 'Term End'),
        ('exam_start', 'Exams Start'),
        ('exam_end', 'Exams End'),
        ('holiday', 'Holiday'),
        ('event', 'School Event'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.title} - {self.school.name}"


class StudentAttendance(models.Model):
    STATUS_CHOICES = (("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused"))
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="present")
    notes = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marked_attendances")

    class Meta:
        unique_together = ("student", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} - {self.date} ({self.status})"


class CanteenItem(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class CanteenPayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)  # e.g. "Lunch", "Snack"
    payment_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="canteen_payments_recorded")

    class Meta:
        ordering = ["-payment_date"]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS ({self.payment_date})"


class BusRoute(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Route A - North"
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class BusPayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    route = models.ForeignKey(BusRoute, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    term_period = models.CharField(max_length=50, blank=True)  # e.g. "Term 1 2025"
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS (Bus)"


class Textbook(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    isbn = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.title} - {self.school.name}"


class TextbookSale(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    sale_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="textbook_sales_recorded")

    class Meta:
        ordering = ["-sale_date"]

    def __str__(self):
        return f"{self.student} - {self.textbook.title} x{self.quantity}"


# Library Management
class LibraryBook(models.Model):
    """Library book catalog"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    isbn = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=100)
    publisher = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50, blank=True)  # Fiction, Science, etc.
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    shelf_location = models.CharField(max_length=50, blank=True)  # e.g., "A-12"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("school", "isbn")

    def __str__(self):
        return f"{self.title} by {self.author}"


class LibraryIssue(models.Model):
    """Track book borrowing"""
    STATUS_CHOICES = (
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
        ('lost', 'Lost'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    book = models.ForeignKey(LibraryBook, on_delete=models.CASCADE)
    issue_date = models.DateField()
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issued_books")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issue_date"]

    def __str__(self):
        return f"{self.student} - {self.book.title}"


# Hostel Management
class Hostel(models.Model):
    """Hostel/Dormitory information"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)  # Boys, Girls, Mixed
    total_beds = models.PositiveIntegerField(default=50)
    warden_name = models.CharField(max_length=100, blank=True)
    warden_phone = models.CharField(max_length=20, blank=True)
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} ({self.type})"


class HostelRoom(models.Model):
    """Individual rooms in hostel"""
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name="rooms")
    room_number = models.CharField(max_length=20)
    floor = models.PositiveIntegerField(default=1)
    total_beds = models.PositiveIntegerField(default=4)
    current_occupancy = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("hostel", "room_number")

    def __str__(self):
        return f"{self.hostel.name} - Room {self.room_number}"


class HostelAssignment(models.Model):
    """Track student hostel assignments"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    room = models.ForeignKey(HostelRoom, on_delete=models.SET_NULL, null=True, blank=True)
    bed_number = models.CharField(max_length=10, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.student} - {self.hostel.name}"


class Announcement(models.Model):
    """School announcements visible to parents/students/staff."""
    TARGET_CHOICES = (
        ("all", "Everyone"),
        ("parents", "Parents"),
        ("students", "Students"),
        ("staff", "Staff Only"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_audience = models.CharField(max_length=20, choices=TARGET_CHOICES, default="all")
    is_pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="announcements_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title


class StaffLeave(models.Model):
    """Staff leave requests and tracking."""
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leave_requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="leave_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.staff.get_full_name()} - {self.start_date} to {self.end_date} ({self.status})"


class ActivityLog(models.Model):
    """Audit trail for important actions."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="activity_logs")
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} - {self.user} at {self.created_at}"


class HostelFee(models.Model):
    """Hostel fee tracking"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    term = models.CharField(max_length=50)  # e.g., "Term 1 2025"
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.student} - {self.hostel.name} - {self.term}"


# Student Health/Medical Records
class StudentHealth(models.Model):
    """Student health information and medical records"""
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="health_record")
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    blood_type = models.CharField(max_length=5, blank=True)  # A+, A-, B+, B-, O+, O-, AB+, AB-
    allergies = models.TextField(blank=True)  # List of allergies
    medical_conditions = models.TextField(blank=True)  # e.g., Asthma, Diabetes
    medications = models.TextField(blank=True)  # Current medications
    emergency_contact = models.CharField(max_length=20, blank=True)  # Emergency phone
    emergency_contact_name = models.CharField(max_length=100, blank=True)  # Emergency contact name
    doctor_name = models.CharField(max_length=100, blank=True)
    doctor_phone = models.CharField(max_length=20, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Health Record - {self.student}"


class HealthVisit(models.Model):
    """Track student health clinic visits"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    visit_date = models.DateTimeField(auto_now_add=True)
    complaint = models.TextField()  # Reason for visit
    diagnosis = models.TextField(blank=True)
    treatment = models.TextField(blank=True)
    visited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_follow_up = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-visit_date"]
    
    def __str__(self):
        return f"{self.student} - {self.visit_date.date()}"


# Inventory Management
class InventoryCategory(models.Model):
    """Categories for inventory items"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Inventory Categories"
    
    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    """School inventory items"""
    CONDITION_CHOICES = (
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    min_quantity = models.PositiveIntegerField(default=5)  # Alert when below this
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    location = models.CharField(max_length=100, blank=True)  # Where it's stored
    description = models.TextField(blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
    
    def __str__(self):
        return f"{self.name} ({self.quantity})"
    
    @property
    def is_low_stock(self):
        return self.quantity <= self.min_quantity


class InventoryTransaction(models.Model):
    """Track inventory movements (additions, removals)"""
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'),
        ('usage', 'Usage'),
        ('damage', 'Damage'),
        ('adjustment', 'Adjustment'),
        ('return', 'Return'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()  # Can be negative for usage
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.transaction_type} - {self.item.name} ({self.quantity})"


# Event Management
class SchoolEvent(models.Model):
    """School events and activities"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    event_type = models.CharField(max_length=50)  # assembly, sports, concert, trip, meeting, other
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    target_audience = models.CharField(max_length=20, default="all")  # all, students, staff, parents
    is_mandatory = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-start_date"]
    
    def __str__(self):
        return self.title


class EventRSVP(models.Model):
    """Track event attendance/confirmation"""
    event = models.ForeignKey(SchoolEvent, on_delete=models.CASCADE, related_name="rsvps")
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    is_attending = models.BooleanField(default=True)
    responded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ("event", "student")
    
    def __str__(self):
        return f"{self.student} - {self.event.title}"


# Online Admission Application
class AdmissionApplication(models.Model):
    """Online admission applications from prospective students"""
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('waitlisted', 'Waitlisted'),
    )
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)  # School can be set if public form has school selection
    
    # Student Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')])
    previous_school = models.CharField(max_length=200, blank=True)
    class_applied_for = models.CharField(max_length=50)
    
    # Parent/Guardian Information
    parent_first_name = models.CharField(max_length=100)
    parent_last_name = models.CharField(max_length=100)
    parent_phone = models.CharField(max_length=20)
    parent_email = models.EmailField(blank=True)
    parent_occupation = models.CharField(max_length=100, blank=True)
    address = models.TextField()
    
    # Additional Information
    reason_for_applying = models.TextField(blank=True)
    medical_conditions = models.TextField(blank=True)
    how_did_you_hear = models.CharField(max_length=200, blank=True)
    
    # Documents (file paths stored as text)
    birth_certificate_path = models.CharField(max_length=255, blank=True)
    previous_report_path = models.CharField(max_length=255, blank=True)
    passport_photo_path = models.CharField(max_length=255, blank=True)
    
    # Status and Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_applications")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # If approved, link to created student
    created_student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="admission_application")
    
    class Meta:
        ordering = ["-applied_at"]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.class_applied_for} ({self.status})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# Certificates
class Certificate(models.Model):
    """Academic certificates (completion, graduation, merit)"""
    CERTIFICATE_TYPES = (
        ('completion', 'Certificate of Completion'),
        ('graduation', 'Graduation Certificate'),
        ('merit', 'Merit Certificate'),
        ('attendance', 'Certificate of Attendance'),
        ('character', 'Certificate of Good Character'),
    )
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='certificates')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    certificate_type = models.CharField(max_length=20, choices=CERTIFICATE_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    issued_date = models.DateField()
    academic_year = models.CharField(max_length=20)  # e.g., "2024/2025"
    term = models.CharField(max_length=50, blank=True)  # e.g., "Term 1"
    
    # PDF stored as bytes (for generated certificates)
    pdf_file = models.BinaryField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issued_certificates")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-issued_date"]
    
    def __str__(self):
        return f"{self.student} - {self.title} ({self.issued_date})"


# ==================== STUDENT ID CARDS ====================
class StudentIDCard(models.Model):
    """Student ID Card management"""
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='id_card')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    card_number = models.CharField(max_length=50, unique=True)
    photo = models.ImageField(upload_to='id_cards/', null=True, blank=True)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.student} - {self.card_number}"


# ==================== PARENT-TEACHER MEETINGS ====================
class PTMeeting(models.Model):
    """Parent-Teacher Meeting scheduling"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    meeting_date = models.DateTimeField()
    location = models.CharField(max_length=200)
    max_slots = models.PositiveIntegerField(default=20)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-meeting_date"]
    
    def __str__(self):
        return f"{self.title} - {self.meeting_date}"
    
    @property
    def booked_slots(self):
        return self.bookings.count()
    
    @property
    def available_slots(self):
        return max(0, self.max_slots - self.booked_slots)


class PTMeetingBooking(models.Model):
    """Individual meeting slot booking"""
    meeting = models.ForeignKey(PTMeeting, on_delete=models.CASCADE, related_name='bookings')
    parent = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'parent'})
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='pt_bookings')
    preferred_time = models.TimeField(null=True, blank=True)
    topics_to_discuss = models.TextField(blank=True)
    is_confirmed = models.BooleanField(default=False)
    booked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("meeting", "parent", "student")
        ordering = ["booked_at"]
    
    def __str__(self):
        return f"{self.parent.get_full_name()} - {self.student}"


# ==================== SPORTS & CLUBS ====================
class Sport(models.Model):
    """Sports teams/activities"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    coach = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coached_sports')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"


class Club(models.Model):
    """School clubs/organizations"""
    CATEGORY_CHOICES = (
        ('academic', 'Academic'),
        ('sports', 'Sports'),
        ('arts', 'Arts & Culture'),
        ('science', 'Science & Tech'),
        ('social', 'Social Service'),
        ('religious', 'Religious'),
        ('other', 'Other'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    sponsor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sponsored_clubs')
    description = models.TextField(blank=True)
    meeting_day = models.CharField(max_length=20, blank=True)  # e.g., "Monday"
    meeting_time = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class StudentSport(models.Model):
    """Student participation in sports"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='sports')
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name='members')
    jersey_number = models.CharField(max_length=10, blank=True)
    position = models.CharField(max_length=50, blank=True)
    joined_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ("student", "sport")
    
    def __str__(self):
        return f"{self.student} - {self.sport.name}"


class StudentClub(models.Model):
    """Student membership in clubs"""
    ROLE_CHOICES = (
        ('member', 'Member'),
        ('secretary', 'Secretary'),
        ('vice_president', 'Vice President'),
        ('president', 'President'),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='club_memberships')
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ("student", "club")
    
    def __str__(self):
        return f"{self.student} - {self.club.name} ({self.role})"


# ==================== EXAM SEATING ====================
class ExamHall(models.Model):
    """Examination halls"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    rows = models.PositiveIntegerField(default=10)
    seats_per_row = models.PositiveIntegerField(default=10)
    description = models.TextField(blank=True)
    
    @property
    def total_seats(self):
        return self.rows * self.seats_per_row
    
    def __str__(self):
        return f"{self.name} ({self.total_seats} seats)"


class SeatingPlan(models.Model):
    """Exam seating arrangements"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    exam_schedule = models.ForeignKey('academics.ExamSchedule', on_delete=models.CASCADE, related_name='seating_plans')
    hall = models.ForeignKey(ExamHall, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("exam_schedule", "hall")
    
    def __str__(self):
        return f"{self.exam_schedule.subject.name} - {self.hall.name}"


class SeatAssignment(models.Model):
    """Individual seat assignments"""
    seating_plan = models.ForeignKey(SeatingPlan, on_delete=models.CASCADE, related_name='seat_assignments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='seat_assignments')
    row_number = models.PositiveIntegerField()
    seat_number = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ("seating_plan", "row_number", "seat_number")
    
    def __str__(self):
        return f"{self.student} - Row {self.row_number}, Seat {self.seat_number}"


# ==================== EXPENSE TRACKING ====================
class ExpenseCategory(models.Model):
    """Categories for school expenses"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"
    
    def __str__(self):
        return f"{self.name} - {self.school.name}"


class Expense(models.Model):
    """School expenses tracking"""
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('cheque', 'Cheque'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    vendor = models.CharField(max_length=200, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    receipt_number = models.CharField(max_length=50, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_expenses')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-expense_date"]
    
    def __str__(self):
        return f"{self.description} - {self.amount} ({self.expense_date})"


class Budget(models.Model):
    """School budget planning"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    academic_year = models.CharField(max_length=20)  # e.g., "2024/2025"
    term = models.CharField(max_length=20, blank=True)  # e.g., "Term 1"
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    @property
    def remaining(self):
        return self.allocated_amount - self.spent_amount
    
    def __str__(self):
        return f"{self.category.name} - {self.academic_year}"


# ==================== STUDENT DISCIPLINE ====================
class DisciplineIncident(models.Model):
    """Track student disciplinary incidents"""
    SEVERITY_CHOICES = (
        ('minor', 'Minor'),
        ('moderate', 'Moderate'),
        ('serious', 'Serious'),
        ('severe', 'Severe'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='discipline_incidents')
    incident_date = models.DateTimeField()
    incident_type = models.CharField(max_length=100)  # e.g., "Fighting", "Late Submission"
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='minor')
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reported_incidents')
    status = models.CharField(max_length=20, default='pending')  # pending, resolved, appealed
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-incident_date"]
    
    def __str__(self):
        return f"{self.student} - {self.incident_type} ({self.severity})"


class BehaviorPoint(models.Model):
    """Track positive behavior points/rewards"""
    POINT_TYPES = (
        ('positive', 'Positive'),
        ('negative', 'Negative'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='behavior_points')
    point_type = models.CharField(max_length=20, choices=POINT_TYPES)
    points = models.IntegerField()  # Can be positive or negative
    reason = models.CharField(max_length=200)
    awarded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='awarded_points')
    awarded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-awarded_at"]
    
    def __str__(self):
        return f"{self.student} - {self.points} points ({self.reason})"


# ==================== ASSIGNMENT SUBMISSION ====================
class AssignmentSubmission(models.Model):
    """Track online assignment submissions"""
    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned'),
    )
    homework = models.ForeignKey('academics.Homework', on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assignment_submissions')
    submission_text = models.TextField(blank=True)
    file_path = models.CharField(max_length=255, blank=True)  # Path to uploaded file
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='graded_submissions')
    graded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ("homework", "student")
        ordering = ["-submitted_at"]
    
    def __str__(self):
        return f"{self.student} - {self.homework.title}"


# ==================== DOCUMENT MANAGEMENT ====================
class StudentDocument(models.Model):
    """Store student documents"""
    DOCUMENT_TYPES = (
        ('birth_certificate', 'Birth Certificate'),
        ('report_card', 'Report Card'),
        ('medical', 'Medical Certificate'),
        ('transfer_letter', 'Transfer Letter'),
        ('passport_photo', 'Passport Photo'),
        ('parent_id', 'Parent ID'),
        ('other', 'Other'),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='documents')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=200)
    file_path = models.CharField(max_length=255)  # Path to stored file
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateField(null=True, blank=True)  # For documents that expire
    
    class Meta:
        ordering = ["-uploaded_at"]
    
    def __str__(self):
        return f"{self.student} - {self.get_document_type_display()}"


# ==================== ALUMNI MANAGEMENT ====================
class Alumni(models.Model):
    """Track past students (alumni)"""
    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, related_name='alumni_record')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    # If student record is deleted, keep alumni info
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    admission_number = models.CharField(max_length=50)
    class_name = models.CharField(max_length=50)  # Last class attended
    graduation_year = models.IntegerField()
    graduation_date = models.DateField(null=True, blank=True)
    
    # Post-graduation info
    current_occupation = models.CharField(max_length=200, blank=True)
    current_institution = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Membership
    is_active_member = models.BooleanField(default=True)
    membership_year = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.graduation_year})"


class AlumniEvent(models.Model):
    """Alumni association events"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    event_date = models.DateTimeField()
    location = models.CharField(max_length=200)
    is_annual = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-event_date"]
    
    def __str__(self):
        return f"{self.title} - {self.event_date.year}"


# ==================== ONLINE EXAM SYSTEM ====================
class OnlineExam(models.Model):
    """Online examination with auto-grading"""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    class_level = models.CharField(max_length=50)  # Target class
    exam_type = models.CharField(max_length=50, default='quiz')  # quiz, test, exam
    duration_minutes = models.PositiveIntegerField(default=30)
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    passing_marks = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_random_questions = models.BooleanField(default=False)
    show_results_immediately = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-start_time"]
    
    def __str__(self):
        return f"{self.title} - {self.subject.name}"


class ExamQuestion(models.Model):
    """Questions for online exams"""
    QUESTION_TYPES = (
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
    )
    exam = models.ForeignKey(OnlineExam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    
    # For multiple choice
    option_a = models.CharField(max_length=500, blank=True)
    option_b = models.CharField(max_length=500, blank=True)
    option_c = models.CharField(max_length=500, blank=True)
    option_d = models.CharField(max_length=500, blank=True)
    correct_answer = models.CharField(max_length=1, blank=True)  # A, B, C, D for MCQ
    
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ["order"]
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."


class ExamAttempt(models.Model):
    """Track student exam attempts"""
    exam = models.ForeignKey(OnlineExam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ("exam", "student")
    
    def __str__(self):
        return f"{self.student} - {self.exam.title}"


class ExamAnswer(models.Model):
    """Individual answers from exam attempts"""
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE)
    answer_given = models.CharField(max_length=500, blank=True)
    is_correct = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ("attempt", "question")


# ==================== TIMETABLE MANAGEMENT ====================
class TimetableSlot(models.Model):
    """Timetable slots for classes"""
    DAYS = (
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)  # e.g., "JHS 1"
    day = models.CharField(max_length=20, choices=DAYS)
    period_number = models.PositiveIntegerField()  # 1, 2, 3, etc.
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'teacher'})
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ("class_name", "day", "period_number")
        ordering = ["day", "period_number"]
    
    def __str__(self):
        return f"{self.class_name} - {self.day} P{self.period_number} - {self.subject.name}"


class TimetableConflict(models.Model):
    """Track timetable conflicts"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    conflict_type = models.CharField(max_length=50)  # teacher_room, room_time, etc.
    slot_1 = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='conflicts_1')
    slot_2 = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='conflicts_2')
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
