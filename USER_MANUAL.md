# Mastex SchoolOS - User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Super Admin Guide](#super-admin-guide)
3. [School Admin Guide](#school-admin-guide)
4. [Teacher Guide](#teacher-guide)
5. [Student Guide](#student-guide)
6. [Parent Guide](#parent-guide)
7. [Features & Modules](#features--modules)

---

## Getting Started

### How to Access the System
1. Open your browser and go to: `https://your-app.onrender.com`
2. Login at `/accounts/login/` with your credentials
3. You will be redirected based on your role

### User Roles
| Role | Access | Description |
|------|--------|-------------|
| Super Admin | `/admin` | Full system control |
| School Admin | `/dashboard` | Full school control |
| Teacher | `/dashboard` | Teaching-related tasks |
| Accountant | `/dashboard` | Financial management |
| Librarian | `/dashboard` | Library management |
| Student | `/portal` | Academic features |
| Parent | `/portal` | Children's information |

---

## Super Admin Guide

### Accessing Django Admin
1. Go to `/admin`
2. Login with super admin credentials
3. You can manage all schools, users, and system settings

### Setting Up a New School
1. Go to **Schools** → **Add School**
2. Fill in school details:
   - Name
   - Address
   - Email
   - Phone
   - Logo (optional)
3. Save the school
4. Go to **Users** → **Add User**
5. Create school admin:
   - Username
   - Email
   - Password
   - Role: `admin`
   - School: Select the school you created
6. The school admin can now login and set up their staff

---

## School Admin Guide

### Dashboard Overview
After login, you'll see the school dashboard with navigation to all features.

### Managing Staff

#### Register New Staff
1. Go to **Users** → **Staff** → **Register Staff**
2. Fill in:
   - Username
   - Email
   - Role (Teacher, Accountant, Librarian, etc.)
   - Password
3. Click **Register Staff**

#### View Staff List
1. Go to **Users** → **Staff**
2. View all staff members
3. Click on a staff name to see details

### Managing Students

#### Register New Student
1. Go to **Students** → **Register Student**
2. Fill in:
   - Username
   - Admission Number
   - Class Name
   - Parent (optional)
   - Date Enrolled
3. Click **Register Student**

#### View Student List
1. Go to **Students** → **Student List**
2. View all students
3. Click on a student to see details

### Academic Management

#### Create Online Exam
1. Go to **Academics** → **Online Exams**
2. Click **Create Exam**
3. Fill in:
   - Title
   - Subject
   - Class Level
   - Duration (minutes)
   - Total Marks
   - Passing Marks
4. Save the exam
5. Add questions:
   - Click **Add Questions** on the exam detail page
   - Enter question text
   - Add 4 options (A, B, C, D)
   - Mark correct answer
   - Set marks
6. When ready, click **Publish Exam** to make it available to students

#### Create Quiz
1. Go to **Academics** → **Quizzes**
2. Click **Create Quiz**
3. Fill in:
   - Title
   - Subject
   - Class Name
   - Duration
   - Passing Score
4. Add questions similarly to exams
5. Quizzes are active immediately

#### Record Student Results
1. Go to **Academics** → **Results**
2. Select class and exam
3. Enter marks for each student
4. Save results

#### Generate Report Cards
1. Go to **Academics** → **Report Cards**
2. Select student and term
3. View/Print report card

### Attendance Management

#### Mark Attendance
1. Go to **Operations** → **Mark Attendance**
2. Select date and class
3. Mark each student as Present/Absent/Late/Excused
4. Save attendance

#### View Attendance
1. Go to **Operations** → **Attendance List**
2. Filter by class and date range
3. View attendance records

### Financial Management

#### Manage Expenses
1. Go to **Finance** → **Expenses**
2. Click **Add Expense**
3. Fill in:
   - Description
   - Amount (GH₵)
   - Category
   - Date
   - Vendor (optional)
   - Payment Method
4. Save expense

#### Manage Budget
1. Go to **Finance** → **Budget**
2. Click **Create Budget**
3. Fill in:
   - Category
   - Allocated Amount
   - Academic Year
   - Term (optional)
4. Save budget

### School Operations

#### Create School Event
1. Go to **Operations** → **Events**
2. Click **Create Event**
3. Fill in:
   - Title
   - Event Type (Academic, Sports, Cultural, etc.)
   - Target Audience (All, Students, Staff, Parents)
   - Start Date & Time
   - End Date & Time (optional)
   - Location
   - Description
   - Mandatory Attendance (checkbox)
4. Save event

#### Manage Library
1. Go to **Operations** → **Library**
2. Add books with details
3. Issue books to students
4. Track returns

#### Manage Hostel
1. Go to **Operations** → **Hostel**
2. Add hostel rooms
3. Assign students to rooms
4. Manage hostel fees

### Communication

#### Send Messages
1. Go to **Messaging** → **Send Message**
2. Select recipients
3. Type message
4. Send

#### Announcements
1. Go to **Operations** → **Announcements**
2. Create announcement
3. Select audience
4. Post announcement

---

## Teacher Guide

### Dashboard
After login, you see teaching-related features.

### Taking Attendance
1. Go to **Attendance** → **Mark Attendance**
2. Select your class
3. Mark students

### Creating Homework
1. Go to **Academics** → **Homework**
2. Click **Create Homework**
3. Fill in:
   - Title
   - Subject
   - Class
   - Description
   - Due Date
4. Save

### Creating Quizzes
1. Go to **Academics** → **Quizzes**
2. Click **Create Quiz**
3. Add questions with correct answers
4. Save quiz

### Creating Online Exams
1. Go to **Operations** → **Online Exams**
2. Click **Create Exam**
3. Add questions
4. Publish when ready

### Managing Results
1. Go to **Academics** → **Results**
2. Enter marks for your subjects
3. Save results

---

## Student Guide

### Accessing Portal
1. Login at `/accounts/login/`
2. You are redirected to `/portal`

### Taking Exams & Quizzes
1. Go to **Online Exams** or **Quizzes**
2. Click **Take Exam/Quiz**
3. Answer all questions
4. Submit when done OR wait for auto-submit when timer runs out

**Important:** The countdown timer shows remaining time. When time runs out, your exam is automatically submitted!

### Viewing Homework
1. Go to **Homework**
2. View assignments
3. Submit homework with attached files

### Checking Results
1. Go to **Results**
2. View your exam and quiz results
3. See scores and feedback

### Library
1. Go to **Library**
2. Search books
3. View your borrowed books

### My Activities
1. Go to **My Activities**
2. View attendance, submissions, and more

---

## Parent Guide

### Accessing Portal
1. Login at `/accounts/login/`
2. You are redirected to `/portal`
3. You see information about your children

### Viewing Children's Information
- **Results**: See your children's academic results
- **Attendance**: View attendance records
- **Fees**: Check fee balances
- **Announcements**: Read school announcements

### PT Meetings
1. Go to **PT Meetings**
2. View scheduled meetings
3. Book slots if available

### Contacting School
1. Go to **Messaging**
2. Send messages to teachers/staff

---

## Features & Modules

### 📚 Academics Module
| Feature | URL | Description |
|---------|-----|-------------|
| Online Exams | `/operations/online-exams/` | Create and take timed exams |
| Quizzes | `/academics/quizzes/` | Create and take quizzes |
| Homework | `/academics/homework/` | Assignments with due dates |
| Results | `/academics/results/` | Student exam results |
| Report Cards | `/academics/report-cards/` | Generate report cards |
| Timetable | `/academics/timetable/` | Class schedules |

### 💰 Finance Module
| Feature | URL | Description |
|---------|-----|-------------|
| Fee Structure | `/fees/` | Manage fee structures |
| Expenses | `/operations/expenses/` | Record expenses |
| Budget | `/operations/budgets/` | Manage budgets |
| Payments | `/payments/` | Payment history |

### 👥 Operations Module
| Feature | URL | Description |
|---------|-----|-------------|
| Attendance | `/operations/attendance/` | Student attendance |
| Library | `/operations/library/` | Book management |
| Hostel | `/operations/hostel/` | Hostel management |
| Events | `/operations/events/` | School events |
| Announcements | `/operations/announcements/` | Post announcements |

### 🏥 Health & Safety Module
| Feature | URL | Description |
|---------|-----|-------------|
| Health Records | `/operations/health/` | Student health info |
| Discipline | `/operations/discipline/` | Behavior records |
| Behavior Points | `/operations/behavior/` | Track behavior |

### 📋 Records Module
| Feature | URL | Description |
|---------|-----|-------------|
| ID Cards | `/operations/id-cards/` | Generate ID cards |
| Certificates | `/operations/certificates/` | Generate certificates |
| Admissions | `/operations/admissions/` | Student admissions |
| Alumni | `/operations/alumni/` | Alumni records |

### 🏅 Extracurricular Module
| Feature | URL | Description |
|---------|-----|-------------|
| Sports | `/operations/sports/` | Sports activities |
| Clubs | `/operations/clubs/` | School clubs |

### 📞 Communication Module
| Feature | URL | Description |
|---------|-----|-------------|
| Messages | `/messaging/send/` | Send messages |
| PT Meetings | `/operations/pt-meetings/` | Parent-teacher meetings |

---

## Frequently Asked Questions

### Q: How do I create a student account?
**A:** School Admin → Students → Register Student → Fill form → Save

### Q: How do students take exams?
**A:** 
1. Exam must be published by admin/teacher
2. Student logs in → Online Exams → Take Exam
3. Answer questions before timer runs out

### Q: How do I add questions to an exam?
**A:** 
1. Create exam
2. Open exam detail
3. Click "Add Questions"
4. Enter question details
5. Save

### Q: Can parents pay fees online?
**A:** Payment portal is configured with Flutterwave. Parents can pay from the fees section.

### Q: How do I generate report cards?
**A:** 
1. Go to Academics → Report Cards
2. Select student and term
3. View/Print report card

### Q: How does the exam timer work?
**A:** When a student starts an exam, a countdown timer begins. When time runs out, the exam is automatically submitted.

---

## Support

For technical support, contact:
- Email: support@mastextech.com
- GitHub: https://github.com/Asamoah-David/Mastex_School_Management_System

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | March 19, 2026 | Initial release with all core features |

---

*Mastex SchoolOS - Making School Management Simple*
