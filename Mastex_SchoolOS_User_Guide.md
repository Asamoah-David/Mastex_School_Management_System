# Mastex SchoolOS
## Complete User Guide for Schools

---

# Table of Contents

1. [Introduction](#1-introduction)
2. [Getting Started](#2-getting-started)
3. [System Roles & Access](#3-system-roles--access)
4. [For School Administrators](#4-for-school-administrators)
5. [For Teachers](#5-for-teachers)
6. [For Students](#6-for-students)
7. [For Parents](#7-for-parents)
8. [Feature Modules](#8-feature-modules)
9. [How-To Guides](#9-how-to-guides)
10. [Troubleshooting](#10-troubleshooting)
11. [Support](#11-support)

---

# 1. Introduction

## What is Mastex SchoolOS?

Mastex SchoolOS is a comprehensive **cloud-based School Management System** designed to streamline all aspects of school administration. From managing student records to conducting online exams, from tracking fees to communicating with parents - Mastex SchoolOS handles it all.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Cloud-Based** | Access from anywhere, any device |
| **Multi-School Support** | Manage multiple schools from one platform |
| **Role-Based Access** | Different users see only what they need |
| **Real-Time Updates** | Information syncs instantly across all devices |
| **Secure** | Bank-level security for your data |
| **Automated** | Reduce manual work with automation |

### What Can You Do?

- ✅ Manage students, teachers, and staff
- ✅ Take attendance electronically
- ✅ Conduct online exams with countdown timers
- ✅ Create and manage quizzes
- ✅ Generate report cards automatically
- ✅ Track fees and expenses
- ✅ Communicate with parents via SMS
- ✅ Generate student ID cards
- ✅ Manage library books
- ✅ Track hostel assignments
- ✅ And much more!

---

# 2. Getting Started

## Accessing the System

### Step 1: Open Your Browser
Open any web browser (Chrome, Firefox, Edge, Safari) on your computer, tablet, or phone.

### Step 2: Go to the Login Page
Navigate to your school's Mastex SchoolOS URL (provided by your system administrator).

### Step 3: Enter Your Credentials
- **Username**: Your unique username
- **Password**: Your secure password

### Step 4: Click Login
You will be automatically redirected based on your role.

## System Requirements

| Device | Minimum | Recommended |
|--------|---------|-------------|
| Computer | Windows 7+, Mac OS X 10.10+ | Windows 10+, Mac OS 11+ |
| Browser | Chrome 80+, Firefox 75+ | Chrome latest |
| Internet | 1 Mbps | 5+ Mbps |
| Mobile | iOS 12+, Android 8+ | iOS 14+, Android 11+ |

---

# 3. System Roles & Access

## Understanding User Roles

Mastex SchoolOS uses a role-based system where each user sees only what they need.

### Role Overview

| Role | Dashboard | Access Level |
|------|----------|--------------|
| **School Admin** | Full Dashboard | Complete school management |
| **Teacher** | Teacher Dashboard | Teaching & attendance |
| **Accountant** | Finance Dashboard | Fees & expenses |
| **Librarian** | Library Dashboard | Books & issues |
| **Nurse** | Health Dashboard | Health records |
| **Student** | My Portal | Academic features |
| **Parent** | My Children | Children's info |

### Super Administrator (Platform Owner)
- Access: `/admin`
- Can manage all schools
- Full system configuration access
- Typically: Organization IT team

---

# 4. For School Administrators

As a School Administrator, you have complete control over your school's operations.

## 4.1 Dashboard Overview

When you log in, you'll see the main dashboard with:
- **Quick Stats**: Student count, today's attendance, pending fees
- **Navigation Menu**: All available modules
- **Recent Activity**: Latest actions in your school

## 4.2 Managing Staff

### Adding New Staff

**Step 1:** Navigate to **Users** → **Staff** → **Register Staff**

**Step 2:** Fill in the registration form:
```
- Username: (unique identifier)
- Email: (valid email address)
- Role: (Teacher, Accountant, Librarian, etc.)
- Password: (temporary password for first login)
```

**Step 3:** Click **Register Staff**

**Step 4:** The new staff member can now login with their credentials.

### Viewing Staff List

1. Go to **Users** → **Staff**
2. View all staff members in a table
3. Click on any name to view full details
4. Use search/filter to find specific staff

## 4.3 Managing Students

### Registering New Student

**Step 1:** Go to **Students** → **Register Student**

**Step 2:** Complete the form:
```
Required Information:
├── Username
├── Admission Number (unique)
├── Class Name (e.g., "Form 1A")
├── Date Enrolled
│
Optional Information:
├── Parent/Guardian Link
├── Date of Birth
├── Contact Information
└── Medical Information
```

**Step 3:** Click **Register Student**

### Student List

View all students: **Students** → **Student List**

Features:
- Search by name or admission number
- Filter by class
- View attendance summary
- View fee status

## 4.4 Managing Attendance

### Marking Daily Attendance

**Step 1:** Navigate to **Operations** → **Mark Attendance**

**Step 2:** Select:
- **Date**: Today's date (default)
- **Class**: Select the class

**Step 3:** Mark each student:
| Status | Meaning |
|--------|---------|
| Present | ✅ Attended school |
| Absent | ❌ Did not attend |
| Late | ⏰ Arrived late |
| Excused | 📋 Approved absence |

**Step 4:** Click **Save Attendance**

### Viewing Attendance Records

1. Go to **Operations** → **Attendance List**
2. Select date range and class
3. View attendance percentage
4. Export to Excel if needed

## 4.5 Managing Academics

### Creating an Online Exam

**Step 1:** Go to **Operations** → **Online Exams**

**Step 2:** Click **Create Exam**

**Step 3:** Fill in exam details:
```
Exam Information:
├── Title: (e.g., "Mid-Term Mathematics")
├── Subject: (select from list)
├── Class Level: (e.g., "Form 1")
├── Duration: (in minutes, e.g., 60)
├── Total Marks: (e.g., 100)
└── Passing Marks: (e.g., 40)
```

**Step 4:** Click **Save Exam**

### Adding Questions to Exam

**Step 1:** From the exam list, click on your exam name

**Step 2:** Click **Add Questions**

**Step 3:** For each question:
```
Question Details:
├── Question Text: (the question itself)
├── Option A: (first answer choice)
├── Option B: (second answer choice)
├── Option C: (third answer choice)
├── Option D: (fourth answer choice)
├── Correct Answer: (A, B, C, or D)
└── Marks: (points for this question)
```

**Step 4:** Click **Save Question**

**Step 5:** Add more questions as needed

### Publishing an Exam

Once your exam has questions:

**Step 1:** Open the exam detail page

**Step 2:** Click the green **Publish Exam** button

**Step 3:** Students can now see and take the exam

### Creating a Quiz

**Step 1:** Go to **Academics** → **Quizzes**

**Step 2:** Click **Create Quiz**

**Step 3:** Similar process to exams

**Note:** Quizzes are active immediately (no publish step needed)

### Recording Student Results

**Step 1:** Navigate to **Academics** → **Results**

**Step 2:** Select:
- Class
- Exam/Quiz
- Subject

**Step 3:** Enter marks for each student

**Step 4:** Click **Save Results**

### Generating Report Cards

**Step 1:** Go to **Academics** → **Report Cards**

**Step 2:** Select:
- Student
- Term
- Academic Year

**Step 3:** View or print the report card

## 4.6 Managing Finances

### Recording Expenses

**Step 1:** Go to **Finance** → **Expenses**

**Step 2:** Click **Add Expense**

**Step 3:** Fill in:
```
Expense Details:
├── Description: (what was purchased)
├── Amount: (in Ghana Cedis)
├── Category: (e.g., Stationery, Repairs)
├── Date: (date of expense)
├── Vendor: (optional - who you paid)
└── Payment Method: (Cash, Bank Transfer, Mobile Money)
```

**Step 4:** Click **Save Expense**

### Managing Budget

**Step 1:** Navigate to **Finance** → **Budget**

**Step 2:** Click **Create Budget**

**Step 3:** Fill in:
```
Budget Details:
├── Category: (expense category)
├── Allocated Amount: (budget amount)
├── Academic Year: (e.g., "2025-2026")
└── Term: (Term 1, 2, or 3 - optional)
```

## 4.7 Managing School Events

### Creating an Event

**Step 1:** Go to **Operations** → **Events**

**Step 2:** Click **Create Event**

**Step 3:** Complete the form:
```
Event Information:
├── Title: (event name)
├── Event Type: (Academic, Sports, Cultural, Holiday, etc.)
├── Target Audience: (All, Students, Staff, Parents)
├── Start Date & Time: (when event begins)
├── End Date & Time: (when event ends - optional)
├── Location: (venue)
├── Description: (details about the event)
└── Mandatory: (checkbox if attendance is required)
```

## 4.8 Library Management

### Adding Books

**Step 1:** Navigate to **Operations** → **Library**

**Step 2:** Click **Add Book**

**Step 3:** Fill in book details:
```
Book Information:
├── Title
├── Author
├── ISBN (optional)
├── Copies Available
└── Description (optional)
```

### Issuing Books

**Step 1:** Go to **Operations** → **Library Issues**

**Step 2:** Click **Issue Book**

**Step 3:** Select:
- Student
- Book
- Due Date

## 4.9 Student ID Cards

### Generating ID Cards

**Step 1:** Go to **Operations** → **ID Cards**

**Step 2:** Click on a student

**Step 3:** Click **Print ID Card**

**Features:**
- Student photo
- Name and class
- Admission number
- School branding

## 4.10 Communication

### Sending Messages

**Step 1:** Navigate to **Messaging** → **Send Message**

**Step 2:** Select recipients:
- All Parents
- All Students
- Specific Class
- Individual contacts

**Step 3:** Type your message

**Step 4:** Click **Send**

### Creating Announcements

**Step 1:** Go to **Operations** → **Announcements**

**Step 2:** Click **Create Announcement**

**Step 3:** Fill in:
```
Announcement Details:
├── Title
├── Content
├── Priority: (Normal, Important, Urgent)
└── Target Audience
```

---

# 5. For Teachers

## 5.1 Dashboard

As a teacher, your dashboard shows:
- Your assigned classes
- Today's schedule
- Pending tasks
- Recent announcements

## 5.2 Taking Attendance

**Step 1:** Go to **Attendance** → **Mark Attendance**

**Step 2:** Select your class

**Step 3:** Mark attendance for each student

**Step 4:** Click **Save**

## 5.3 Creating Homework

**Step 1:** Navigate to **Academics** → **Homework**

**Step 2:** Click **Create Homework**

**Step 3:** Fill in:
```
Homework Details:
├── Title
├── Subject
├── Class
├── Description
├── Due Date
└── Attachment (optional)
```

## 5.4 Creating Quizzes

**Step 1:** Go to **Academics** → **Quizzes**

**Step 2:** Click **Create Quiz**

**Step 3:** Add quiz details and questions

**Step 4:** Save the quiz (automatically active)

## 5.5 Creating Online Exams

**Step 1:** Go to **Operations** → **Online Exams**

**Step 2:** Create exam and add questions

**Step 3:** When ready, click **Publish**

## 5.6 Managing Results

**Step 1:** Navigate to **Academics** → **Results**

**Step 2:** Select your subject and class

**Step 3:** Enter marks for each student

**Step 4:** Save results

---

# 6. For Students

## 6.1 Accessing Your Portal

1. Go to the school login page
2. Enter your username and password
3. You are automatically redirected to **My Portal**

## 6.2 Taking Online Exams

**Step 1:** Go to **Online Exams**

**Step 2:** Find your exam in the list

**Step 3:** Click **Take Exam**

### Important: The Countdown Timer

⚠️ **CRITICAL INFORMATION:**

When you start an exam:
- A countdown timer appears at the top
- The timer shows remaining time in **MM:SS** format
- When time runs out, your exam is **automatically submitted**

### Timer Color Guide

| Color | Time Remaining | Meaning |
|-------|----------------|---------|
| 🔵 Blue | More than 5 minutes | Normal - plenty of time |
| 🟠 Orange | 5 minutes or less | Warning - start wrapping up |
| 🔴 Red | 1 minute or less | Urgent - submit now! |

### Exam Tips

✅ **Before Starting:**
- Find a quiet place
- Ensure stable internet
- Have paper and pen ready

✅ **During Exam:**
- Answer questions you know first
- Flag difficult questions to revisit
- Keep an eye on the timer
- Submit well before time runs out

✅ **When Time Runs Out:**
- Don't panic
- Your answers are automatically saved
- You'll see your results immediately after

## 6.3 Taking Quizzes

1. Go to **Quizzes**
2. Click **Take Quiz** on available quizzes
3. Answer all questions
4. Submit when done
5. View your score immediately

## 6.4 Viewing Homework

1. Go to **Homework**
2. View assignments with due dates
3. Complete and submit homework
4. Attach files if required

## 6.5 Checking Results

1. Navigate to **Results**
2. View all your exam and quiz scores
3. See your overall performance

## 6.6 Library

1. Go to **Library**
2. Search for books
3. View your borrowed books
4. Check due dates

---

# 7. For Parents

## 7.1 Accessing Parent Portal

1. Go to the school login page
2. Enter your parent account credentials
3. You are redirected to **My Children** dashboard

## 7.2 Viewing Children's Information

Your dashboard shows all linked children with:
- Current class
- Recent attendance
- Fee status
- Announcements

## 7.3 Viewing Results

**Step 1:** Click on your child's name

**Step 2:** Go to **Results**

**Step 3:** View:
- Exam scores
- Quiz results
- Term reports

## 7.4 Checking Attendance

1. Select your child
2. Go to **Attendance**
3. View daily attendance records
4. See absence notifications

## 7.5 Fee Management

1. Navigate to **Fees**
2. View outstanding balances
3. Make payments online (if available)
4. View payment history

## 7.6 PT Meetings

**Step 1:** Go to **PT Meetings**

**Step 2:** View scheduled meetings

**Step 3:** Book available slots

**Step 4:** Attend meetings with teachers

## 7.7 Receiving Announcements

- All school announcements appear on your dashboard
- Important announcements sent via SMS (if enabled)
- Check regularly for updates

---

# 8. Feature Modules

## 8.1 Academics Module

| Feature | Description | URL |
|---------|-------------|-----|
| Online Exams | Timed exams with auto-submit | `/operations/online-exams/` |
| Quizzes | Quick assessments | `/academics/quizzes/` |
| Homework | Assignments with due dates | `/academics/homework/` |
| Results | Student academic scores | `/academics/results/` |
| Report Cards | Automated report generation | `/academics/report-cards/` |
| Timetable | Class schedules | `/academics/timetable/` |

## 8.2 Finance Module

| Feature | Description | URL |
|---------|-------------|-----|
| Fee Structure | Define fees per class | `/fees/` |
| Expenses | Record school spending | `/operations/expenses/` |
| Budget | Plan school budget | `/operations/budgets/` |
| Payments | View payment history | `/payments/` |

## 8.3 Operations Module

| Feature | Description | URL |
|---------|-------------|-----|
| Attendance | Daily attendance tracking | `/operations/attendance/` |
| Library | Book management | `/operations/library/` |
| Hostel | Dormitory management | `/operations/hostel/` |
| Events | School calendar | `/operations/events/` |
| Announcements | School notices | `/operations/announcements/` |

## 8.4 Health & Safety Module

| Feature | Description | URL |
|---------|-------------|-----|
| Health Records | Student medical info | `/operations/health/` |
| Discipline | Behavior tracking | `/operations/discipline/` |
| Behavior Points | Reward/penalty system | `/operations/behavior/` |

## 8.5 Records Module

| Feature | Description | URL |
|---------|-------------|-----|
| ID Cards | Generate student IDs | `/operations/id-cards/` |
| Certificates | Issue certificates | `/operations/certificates/` |
| Admissions | Application process | `/operations/admissions/` |
| Alumni | Former students | `/operations/alumni/` |

## 8.6 Communication Module

| Feature | Description | URL |
|---------|-------------|-----|
| Messages | Send SMS to parents | `/messaging/send/` |
| PT Meetings | Schedule meetings | `/operations/pt-meetings/` |

---

# 9. How-To Guides

## How to Set Up a New School Year

1. **Update Academic Calendar**
   - Go to Settings
   - Set new academic year dates

2. **Create New Classes**
   - Add class names for new year
   - Assign class teachers

3. **Register New Students**
   - Admit new students
   - Assign to classes

4. **Update Fee Structure**
   - Review and update fees
   - Set due dates

## How to Conduct a Successful Online Exam

### For Administrators/Teachers:

1. **Plan the Exam**
   - Decide on duration (consider 1-2 minutes per question)
   - Set appropriate passing marks

2. **Create Questions**
   - Use clear, unambiguous language
   - Ensure only one correct answer
   - Mix easy and challenging questions

3. **Test Before Publishing**
   - Preview the exam
   - Check all questions display correctly

4. **Publish and Monitor**
   - Publish the exam
   - Monitor student attempts
   - Be available to address technical issues

### For Students:

1. **Prepare**
   - Find a quiet location
   - Ensure stable internet
   - Charge your device

2. **Start Early**
   - Log in 5 minutes before
   - Read all instructions

3. **Manage Time**
   - Keep the timer visible
   - Don't spend too long on one question

4. **Submit**
   - Review if time permits
   - Submit before timer ends

## How to Generate Report Cards

1. Ensure all results are entered
2. Go to **Academics** → **Report Cards**
3. Select student
4. Select term
5. System generates report automatically
6. Print or export as PDF

## How to Send Bulk Messages to Parents

1. Navigate to **Messaging** → **Send Message**
2. Select recipient type:
   - All Parents
   - Parents of specific class
   - Individual parents
3. Compose your message
4. Review and send
5. (Optional) Send as SMS for urgent messages

---

# 10. Troubleshooting

## Common Issues and Solutions

### Login Issues

| Problem | Solution |
|---------|----------|
| Forgot password | Click "Forgot Password" link |
| Account locked | Contact school administrator |
| Wrong credentials | Check CAPS LOCK is off |

### Exam Issues

| Problem | Solution |
|---------|----------|
| Timer not starting | Refresh the page and start again |
| Answers not saving | Click Save Answer before moving on |
| Connection lost | Reconnect - answers may still be saved |
| Timer ran out | Don't worry - answers were auto-submitted |

### Technical Problems

| Problem | Solution |
|---------|----------|
| Page won't load | Clear browser cache and cookies |
| Slow performance | Check internet connection |
| Forms not submitting | Try a different browser |
| File upload fails | Check file size (max 5MB) |

### Contact Support

If issues persist:
1. Take a screenshot of the error
2. Note the time it occurred
3. Contact your school IT support or Mastex support

---

# 11. Support

## Getting Help

### Within Your School
- **School IT Support**: Contact your school's tech support team
- **School Admin**: For user account issues

### Mastex SchoolOS Support
- **Email**: support@mastextech.com
- **Documentation**: Available in system Help section

## Reporting Issues

When reporting an issue, include:
1. Your name and role
2. School name
3. Browser and version
4. Steps to reproduce the issue
5. Screenshots if possible
6. Time the issue occurred

---

# Appendix A: Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl + S | Save current form |
| Ctrl + P | Print current page |
| Ctrl + F | Find/Search |
| Esc | Close dialog/ popup |

---

# Appendix B: Glossary

| Term | Definition |
|------|------------|
| **SaaS** | Software as a Service - cloud-based software |
| **Dashboard** | Main page with overview and navigation |
| **Portal** | User-specific area with personalized content |
| **Role** | User type determining access levels |
| **Attendance** | Record of presence/absence |
| **Term** | Academic period (usually 3 per year) |
| **Passing Marks** | Minimum score to pass an exam |
| **Auto-Submit** | Automatic submission when time expires |

---

# Appendix C: System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Mastex SchoolOS                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │   Super     │    │   School    │    │   Parent    │   │
│  │   Admin     │    │   Admin     │    │   Portal    │   │
│  └─────────────┘    └─────────────┘    └─────────────┘   │
│         │                  │                  │            │
│         └──────────────────┼──────────────────┘            │
│                            │                                │
│         ┌──────────────────┼──────────────────┐            │
│         │                  │                  │            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   Teacher   │    │   Student   │    │   Staff     │  │
│  │  Dashboard  │    │    Portal   │    │  Dashboard  │  │
│  └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                             │
│                     ┌─────────────┐                        │
│                     │    PostgreSQL    │                   │
│                     │     Database      │                   │
│                     └─────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

**Document Version:** 1.0  
**Last Updated:** March 2026  
**© 2026 Mastex SchoolOS. All rights reserved.**

---

*Mastex SchoolOS - Empowering Education Through Technology*
