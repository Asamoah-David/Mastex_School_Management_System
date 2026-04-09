"""
School-scoped operations: attendance, canteen, bus, textbooks, and more.
Each school manages these independently.

Models are split into focused sub-modules but all remain importable
from operations.models for Django compatibility.
"""

from operations.models.attendance import (
    TeacherAttendance,
    AcademicCalendar,
    StudentAttendance,
)
from operations.models.canteen import (
    CanteenItem,
    CanteenPayment,
)
from operations.models.transport import (
    BusRoute,
    BusPayment,
    Textbook,
    TextbookSale,
)
from operations.models.library import (
    LibraryBook,
    LibraryIssue,
)
from operations.models.hostel import (
    Hostel,
    HostelRoom,
    HostelAssignment,
    HostelFee,
)
from operations.models.announcements import (
    Announcement,
    StaffLeave,
    ActivityLog,
)
from operations.models.health import (
    StudentHealth,
    HealthVisit,
)
from operations.models.inventory import (
    InventoryCategory,
    InventoryItem,
    InventoryTransaction,
)
from operations.models.events import (
    SchoolEvent,
    EventRSVP,
    PTMeeting,
    PTMeetingBooking,
)
from operations.models.admission import (
    AdmissionApplication,
    Certificate,
    StudentIDCard,
    StaffIDCard,
)
from operations.models.sports import (
    Sport,
    Club,
    StudentSport,
    StudentClub,
)
from operations.models.exams import (
    ExamHall,
    SeatingPlan,
    SeatAssignment,
    OnlineExam,
    ExamQuestion,
    ExamAttempt,
    ExamAnswer,
)
from operations.models.finance import (
    ExpenseCategory,
    Expense,
    Budget,
)
from operations.models.discipline import (
    DisciplineIncident,
    BehaviorPoint,
)
from operations.models.submissions import (
    AssignmentSubmission,
)
from operations.models.documents import (
    StudentDocument,
)
from operations.models.alumni import (
    Alumni,
    AlumniEvent,
)
from operations.models.timetable import (
    TimetableSlot,
    TimetableConflict,
)

__all__ = [
    # attendance
    "TeacherAttendance", "AcademicCalendar", "StudentAttendance",
    # canteen
    "CanteenItem", "CanteenPayment",
    # transport
    "BusRoute", "BusPayment", "Textbook", "TextbookSale",
    # library
    "LibraryBook", "LibraryIssue",
    # hostel
    "Hostel", "HostelRoom", "HostelAssignment", "HostelFee",
    # announcements
    "Announcement", "StaffLeave", "ActivityLog",
    # health
    "StudentHealth", "HealthVisit",
    # inventory
    "InventoryCategory", "InventoryItem", "InventoryTransaction",
    # events
    "SchoolEvent", "EventRSVP", "PTMeeting", "PTMeetingBooking",
    # admission
    "AdmissionApplication", "Certificate", "StudentIDCard", "StaffIDCard",
    # sports
    "Sport", "Club", "StudentSport", "StudentClub",
    # exams
    "ExamHall", "SeatingPlan", "SeatAssignment", "OnlineExam", "ExamQuestion", "ExamAttempt", "ExamAnswer",
    # finance
    "ExpenseCategory", "Expense", "Budget",
    # discipline
    "DisciplineIncident", "BehaviorPoint",
    # submissions
    "AssignmentSubmission",
    # documents
    "StudentDocument",
    # alumni
    "Alumni", "AlumniEvent",
    # timetable
    "TimetableSlot", "TimetableConflict",
]
