# Mastex SchoolOS – System Overview

## What You Have Built

A **cloud-hosted School Management System** deployed on Render with PostgreSQL. It supports multiple schools (SaaS): each school manages its own students, staff, fees, attendance, canteen, bus, and textbooks independently.

---

## 🎯 Navigation Audit Summary (Updated)

### Role-Based Navigation Access

| Role | Dashboard | Key Features in Nav |
|------|----------|---------------------|
| **Super Admin** | Platform Dashboard | Schools, Django Admin, Activity Log |
| **School Admin** | School Dashboard | All school features - Academics, Users, Finance, Operations |
| **Deputy Head/HOD** | School Dashboard | Staff, Students, Attendance, Discipline |
| **Teacher** | School Dashboard | **Quizzes, Online Exams, Create Quiz/Exam**, Attendance, Homework, Timetable |
| **Accountant** | School Dashboard | Finance, Fee Structure, Expenses, Budget |
| **Librarian** | School Dashboard | Library Books, Book Issues |
| **Admission Officer** | School Dashboard | Admissions, Students, Documents |
| **School Nurse** | School Dashboard | Health Records, Health Visits |
| **Admin Assistant** | School Dashboard | Inventory, Announcements, Documents |
| **Student** | My Portal | **Quizzes, Online Exams, My Submissions**, My Results, Homework, Library Books, Hostel, Sports & Clubs |
| **Parent** | My Children | Results, Fees, PT Meetings, Announcements |

---

## URL Structure (Final)

| URL | Who uses it | Purpose |
|-----|-------------|---------|
| **/admin** | Super Admin (you) | Django Admin – schools, users, all data |
| **/login** | Everyone | Redirects to `/accounts/login/` (user login page) |
| **/accounts/login/** | Schools, staff, parents, students | User login |
| **/dashboard** or **/** | School Admin, Teachers, Super Admin | Dashboard (school-scoped or platform) |
| **/portal** | Parents, Students | Parent portal (children) or student portal (own info) |

---

## User Roles & Access

1. **Super Admin (you)**  
   - Access: `/admin`  
   - Manages: schools, system config, global data. No `school` on user – sees all schools.

2. **School Admin**  
   - Access: `/dashboard` (after login)  
   - User has `role=admin` and `school` set.  
   - Manages: staff, students, attendance, canteen, bus, textbooks, fees for **their school only**.

3. **Staff / Teachers**  
   - Access: `/dashboard`  
   - User has `role=teacher` and `school` set.  
   - **Can create Quizzes and Online Exams** for their classes.

4. **Parents**  
   - Access: `/portal`  
   - Sees list of their children (students linked via `Student.parent`).

5. **Students**  
   - Access: `/portal`  
   - **Can take Quizzes and Online Exams** - sees their own student record with all academic features.

---

## New Additions (March 2026)

### 1. Registration & details
- **Staff registration** (`/accounts/staff/register/`) – School admin adds teachers/school admins (username, email, role, password).
- **Staff list** (`/accounts/staff/`) – List staff; **staff detail** (`/accounts/staff/<id>/`) – View one staff.
- **Student registration** (`/students/register/`) – School admin adds students (username, admission number, class, optional parent).
- **Student list** (`/students/list/`) – List students; **student detail** (`/students/detail/<id>/`) – View one student.

### 2. Operations (per school)
- **Attendance** – `StudentAttendance`: date, status (present/absent/late/excused), per student.  
  - Mark: `/operations/attendance/mark/`  
  - List: `/operations/attendance/`
- **Canteen** – `CanteenItem` (name, price), `CanteenPayment` (student, amount, description).  
  - Items: `/operations/canteen/`  
  - Payments: `/operations/canteen/payments/`
- **Bus** – `BusRoute` (name, fee_per_term), `BusPayment` (student, amount, term, paid).  
  - Routes: `/operations/bus/`  
  - Payments: `/operations/bus/payments/`
- **Textbooks** – `Textbook` (title, price, stock), `TextbookSale` (student, textbook, quantity, amount).  
  - Books: `/operations/textbooks/`  
  - Sales: `/operations/textbooks/sales/`

### 3. Academic Features
- **Online Exams** – Create exams with questions, publish when ready, **countdown timer** for students, **auto-submit** when time expires
- **Quizzes** – Create quizzes with questions, students can take quizzes
- **Homework** – Create homework assignments, students can submit
- **Report Cards** – Generate and view student report cards
- **Results** – Enter and manage student exam results
- **Timetable** – View class timetables

### 4. School Management Operations
- **Events** – Create school events with type, audience, date/time, mandatory flag
- **Clubs & Sports** – Manage school clubs and sports activities
- **Hostel** – Manage hostel rooms, fees, and assignments
- **Library** – Manage books, catalog, and book issues
- **Announcements** – Post announcements for school community
- **Documents** – Upload and manage school documents

### 5. Financial Management
- **Expenses** – Record school expenses with categories, payment methods, receipt numbers
- **Budget** – Create and manage school budgets by category, academic year, term
- **Fee Structure** – Define fee structures per class/term
- **Inventory** – Track school inventory items

### 6. Health & Safety
- **Health Records** – Student health records and allergies
- **Health Visits** – Track health clinic visits
- **Discipline** – Student discipline records and behavior points

### 7. Communication
- **Messages** – Send messages to parents/students
- **PT Meetings** – Parent-Teacher meeting scheduling

### 8. Identity & Records
- **ID Cards** – Generate and print student ID cards
- **Certificates** – Generate school certificates
- **Admission** – Student admission application and approval
- **Alumni** – Track alumni events and alumni records

### 9. QR Code Attendance System (NEW!)
- **QR Code Scanner** – Scan student ID cards to mark attendance quickly
  - Scanner Page: `/operations/attendance/qr-scanner/`
  - Summary Page: `/operations/attendance/qr-summary/`
  - Bulk QR Generation: `/operations/attendance/qr-codes/<class_name>/`
- **How it works:**
  1. Generate QR codes for all students in a class
  2. Print and attach QR codes to student ID cards
  3. Teachers scan QR codes during attendance
  4. Attendance is marked automatically!
- **Benefits:**
  - ⚡ Fast - Mark attendance in seconds
  - ✅ Accurate - No manual entry errors
  - 📊 Real-time stats - Live attendance dashboard

---

## UI/UX Improvements

### Role-Based Permissions
- **Students** see "Take Exam" button for published online exams
- **Students/Parents** do NOT see Edit/Delete buttons on events
- **Staff** see full management options
- Delete button added to Quiz list for staff

### Form Field Corrections
- **Expense Form**: `date` → `expense_date`, added `payment_method`, `receipt_number`
- **Budget Form**: `title` → `category`, `total_amount` → `allocated_amount`, `period` → `academic_year`, `term`
- **Event Form**: `event_date` + `event_time` → `start_date` (datetime-local), added `event_type`, `target_audience`, `is_mandatory`, `end_date`

### New Templates Created
- `online_exam_take.html` - Student exam interface with countdown timer
- `online_exam_result.html` - Exam results display
- `school_event_detail.html` - Event details with RSVPs

---

## Core Features Already in Place

- Student & school management  
- Fee tracking & payment records (Paystack)  
- Messaging module (SMS – MNotify)  
- AI assistant module  
- Role-based access (admin, teacher, student, parent)  
- Professional UI (Mastex branding, login, dashboard, sidebar)
- **Online Quizzes & Exams** with countdown timer and auto-submit
- **Multi-school admission** with school selection dropdown

---

## Features Still Useful Before Selling

- **School registration page** – Public form for new schools to sign up (create School + first admin).
- **Parent payment portal** – Pay fees from `/portal` (Paystack already configured).
- **SMS notifications** – Already integrated; wire to payment confirmations and announcements.

---

## Deployment

- **Backend**: Django (Render)  
- **Database**: PostgreSQL (Render)  
- **Frontend**: Django templates (Mastex theme)  
- **Auth**: Session-based login; JWT for API if needed.

---

## Steps to Get Ready for Schools

1. Create a **School** in Django Admin and assign a **User** (role=admin, school=that school).  
2. That school admin logs in at `/accounts/login/` and uses **Register staff** / **Register student**.  
3. Mark **attendance**, add **canteen items**, **bus routes**, **textbooks** in Django Admin (or add forms later).  
4. Link **parents** to students; parents log in and use **/portal**.  
5. Connect **payment gateway** to fee payment flow for parents.  
6. Test with sample schools and students, then add branding and any extra UI.

---

## Integration Status

| Service | Status | Purpose |
|---------|--------|---------|
| MNotify SMS | ✅ Configured | Admissions, Announcements, Fee Reminders |
| Paystack | ✅ Configured | School Fee Payments & Subscriptions |
| Gemini AI | ✅ Configured | AI Assistant (Report Comments) |

---

## Last Updated

**System Overview Updated:** March 24, 2026  
**GitHub:** https://github.com/Asamoah-David/Mastex_School_Management_System
