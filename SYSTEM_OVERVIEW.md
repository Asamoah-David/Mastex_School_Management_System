# Mastex SchoolOS – System Overview

## What You Have Built

A **cloud-hosted School Management System** deployed on Render with PostgreSQL. It supports multiple schools (SaaS): each school manages its own students, staff, fees, attendance, canteen, bus, and textbooks independently.

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
   - Same school-scoped sidebar: staff, students, attendance, canteen, bus, textbooks.

4. **Parents**  
   - Access: `/portal`  
   - Sees list of their children (students linked via `Student.parent`).

5. **Students**  
   - Access: `/portal`  
   - Sees own student record (admission number, class, school).

---

## New Additions (This Build)

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

All operations are filtered by `request.user.school` (school admin/teacher). Canteen/bus/textbook **records** are created in Django Admin for now; list and payment/sale views are in the dashboard.

### 3. Models added
- **Student**: `class_name`, `date_enrolled` (optional).
- **operations** app: `StudentAttendance`, `CanteenItem`, `CanteenPayment`, `BusRoute`, `BusPayment`, `Textbook`, `TextbookSale`.

### 4. Portals & login
- **Login** – Role-based redirect: parent/student → `/portal`; admin/teacher → `/dashboard` (home).
- **Portal** – `/portal`: parents see children; students see own info.
- **Dashboard** – School-scoped when `user.school` is set: sidebar shows Staff, Students, Attendance, Canteen, Bus, Textbooks. Platform admin (no school) sees Schools, Students, Fees, Django Admin.

---

## Core Features Already in Place

- Student & school management  
- Fee tracking & payment records (Flutterwave/Stripe)  
- Messaging module (SMS – MNotify)  
- AI assistant module  
- Role-based access (admin, teacher, student, parent)  
- Professional UI (Mastex branding, login, dashboard, sidebar)

---

## Features Still Useful Before Selling

- **School registration page** – Public form for new schools to sign up (create School + first admin).
- **Parent payment portal** – Pay fees from `/portal` (e.g. Flutterwave/Paystack).
- **SMS notifications** – Already integrated; wire to payment confirmations and announcements.
- **Add/edit canteen, bus, textbook from dashboard** – Currently add via Django Admin; optional forms in app.

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

This document reflects the current system and new additions as of this build.
