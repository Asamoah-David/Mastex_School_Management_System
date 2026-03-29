-- ============================================================
-- Supabase RLS Security Migration
-- Enables Row Level Security on all tables for Mastex SchoolOS
-- Created: 2026-03-25
-- Updated: 2026-03-28 (Removed outdated M2M table references - secondary_roles is now TextField)
-- ============================================================

-- ============================================================
-- SECTION 1: ENABLE RLS ON ALL TABLES
-- ============================================================

-- academics tables
ALTER TABLE academics_subject ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_examschedule ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_term ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_examtype ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_homework ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_quiz ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_quizattempt ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_gradeboundary ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_quizanswer ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_quizquestion ENABLE ROW LEVEL SECURITY;
ALTER TABLE academics_timetable ENABLE ROW LEVEL SECURITY;

-- accounts tables
-- NOTE: secondary_roles is now a TextField on accounts_user (not a separate table)
ALTER TABLE accounts_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_user_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_user_assigned_subjects ENABLE ROW LEVEL SECURITY;
-- Removed: accounts_user_secondary_roles (now TextField, not M2M)
ALTER TABLE accounts_user_user_permissions ENABLE ROW LEVEL SECURITY;

-- auth tables (Django auth)
ALTER TABLE auth_group ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_permission ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_group_permissions ENABLE ROW LEVEL SECURITY;

-- django system tables
ALTER TABLE django_content_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE django_admin_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE django_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE django_session ENABLE ROW LEVEL SECURITY;

-- finance tables
ALTER TABLE finance_fee ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance_feestructure ENABLE ROW LEVEL SECURITY;

-- operations tables
ALTER TABLE operations_expensecategory ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_busroute ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_buspayment ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_schoolevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_activitylog ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_admissionapplication ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_alumni ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_alumnievent ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_announcement ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_academiccalendar ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_behaviorpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_club ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_disciplineincident ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_eventrsvp ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_assignmentsubmission ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_canteenitem ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_canteenpayment ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_certificate ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_expense ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_examhall ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_examattempt ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_hostel ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_hostelassignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_hostelfee ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_examquestion ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_healthvisit ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_hostelroom ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_ptmeetingbooking ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_inventorytransaction ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_librarybook ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_libraryissue ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_ptmeeting ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_inventorycategory ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_seatassignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_onlineexam ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_staffidcard ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_studentattendance ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_studentidcard ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_textbooksale ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_sport ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_staffleave ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_studentclub ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_studentdocument ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_studenthealth ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_studentsport ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_teacherattendance ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_textbook ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_timetableconflict ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_timetableslot ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_examanswer ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_inventoryitem ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations_seatingplan ENABLE ROW LEVEL SECURITY;

-- schools tables
ALTER TABLE schools_school ENABLE ROW LEVEL SECURITY;
ALTER TABLE schools_schoolfeature ENABLE ROW LEVEL SECURITY;

-- students tables
ALTER TABLE students_student ENABLE ROW LEVEL SECURITY;
ALTER TABLE students_schoolclass ENABLE ROW LEVEL SECURITY;
ALTER TABLE students_studentachievement ENABLE ROW LEVEL SECURITY;
ALTER TABLE students_studentactivity ENABLE ROW LEVEL SECURITY;
ALTER TABLE students_studentdiscipline ENABLE ROW LEVEL SECURITY;
ALTER TABLE students_absencerequest ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- SECTION 2: CREATE BYPASS POLICIES FOR SERVICE ROLE
-- Service role bypass is needed for Django direct database access
-- ============================================================

-- academics policies
CREATE POLICY "service_bypass_academics_subject" ON academics_subject FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_examschedule" ON academics_examschedule FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_term" ON academics_term FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_examtype" ON academics_examtype FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_homework" ON academics_homework FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_quiz" ON academics_quiz FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_quizattempt" ON academics_quizattempt FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_result" ON academics_result FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_gradeboundary" ON academics_gradeboundary FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_quizanswer" ON academics_quizanswer FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_quizquestion" ON academics_quizquestion FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_academics_timetable" ON academics_timetable FOR ALL TO service_role USING (true) WITH CHECK (true);

-- accounts policies
-- NOTE: secondary_roles is now a TextField on accounts_user (not a separate table)
CREATE POLICY "service_bypass_accounts_user" ON accounts_user FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_accounts_user_groups" ON accounts_user_groups FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_accounts_user_assigned_subjects" ON accounts_user_assigned_subjects FOR ALL TO service_role USING (true) WITH CHECK (true);
-- Removed: accounts_user_secondary_roles policy (now TextField, not M2M)
CREATE POLICY "service_bypass_accounts_user_user_permissions" ON accounts_user_user_permissions FOR ALL TO service_role USING (true) WITH CHECK (true);

-- auth policies
CREATE POLICY "service_bypass_auth_group" ON auth_group FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_auth_permission" ON auth_permission FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_auth_group_permissions" ON auth_group_permissions FOR ALL TO service_role USING (true) WITH CHECK (true);

-- django policies
CREATE POLICY "service_bypass_django_content_type" ON django_content_type FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_django_admin_log" ON django_admin_log FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_django_migrations" ON django_migrations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_django_session" ON django_session FOR ALL TO service_role USING (true) WITH CHECK (true);

-- finance policies
CREATE POLICY "service_bypass_finance_fee" ON finance_fee FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_finance_feestructure" ON finance_feestructure FOR ALL TO service_role USING (true) WITH CHECK (true);

-- operations policies
CREATE POLICY "service_bypass_operations_expensecategory" ON operations_expensecategory FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_busroute" ON operations_busroute FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_buspayment" ON operations_buspayment FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_schoolevent" ON operations_schoolevent FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_activitylog" ON operations_activitylog FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_admissionapplication" ON operations_admissionapplication FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_alumni" ON operations_alumni FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_alumnievent" ON operations_alumnievent FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_announcement" ON operations_announcement FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_academiccalendar" ON operations_academiccalendar FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_behaviorpoint" ON operations_behaviorpoint FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_club" ON operations_club FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_disciplineincident" ON operations_disciplineincident FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_eventrsvp" ON operations_eventrsvp FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_assignmentsubmission" ON operations_assignmentsubmission FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_budget" ON operations_budget FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_canteenitem" ON operations_canteenitem FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_canteenpayment" ON operations_canteenpayment FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_certificate" ON operations_certificate FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_expense" ON operations_expense FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_examhall" ON operations_examhall FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_examattempt" ON operations_examattempt FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_hostel" ON operations_hostel FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_hostelassignment" ON operations_hostelassignment FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_hostelfee" ON operations_hostelfee FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_examquestion" ON operations_examquestion FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_healthvisit" ON operations_healthvisit FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_hostelroom" ON operations_hostelroom FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_ptmeetingbooking" ON operations_ptmeetingbooking FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_inventorytransaction" ON operations_inventorytransaction FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_librarybook" ON operations_librarybook FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_libraryissue" ON operations_libraryissue FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_ptmeeting" ON operations_ptmeeting FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_inventorycategory" ON operations_inventorycategory FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_seatassignment" ON operations_seatassignment FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_onlineexam" ON operations_onlineexam FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_staffidcard" ON operations_staffidcard FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_studentattendance" ON operations_studentattendance FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_studentidcard" ON operations_studentidcard FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_textbooksale" ON operations_textbooksale FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_sport" ON operations_sport FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_staffleave" ON operations_staffleave FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_studentclub" ON operations_studentclub FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_studentdocument" ON operations_studentdocument FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_studenthealth" ON operations_studenthealth FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_studentsport" ON operations_studentsport FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_teacherattendance" ON operations_teacherattendance FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_textbook" ON operations_textbook FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_timetableconflict" ON operations_timetableconflict FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_timetableslot" ON operations_timetableslot FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_examanswer" ON operations_examanswer FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_inventoryitem" ON operations_inventoryitem FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_operations_seatingplan" ON operations_seatingplan FOR ALL TO service_role USING (true) WITH CHECK (true);

-- schools policies
CREATE POLICY "service_bypass_schools_school" ON schools_school FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_schools_schoolfeature" ON schools_schoolfeature FOR ALL TO service_role USING (true) WITH CHECK (true);

-- students policies
CREATE POLICY "service_bypass_students_student" ON students_student FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_students_schoolclass" ON students_schoolclass FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_students_studentachievement" ON students_studentachievement FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_students_studentactivity" ON students_studentactivity FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_students_studentdiscipline" ON students_studentdiscipline FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_students_absencerequest" ON students_absencerequest FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================
-- SECTION 3: SECURE SENSITIVE COLUMNS
-- ============================================================

-- Block password column access from non-service roles
-- The password column in accounts_user should never be exposed via API
COMMENT ON COLUMN accounts_user.password IS 'Sensitive: Password hash - NEVER expose via API';

-- Block session_key access
COMMENT ON COLUMN django_session.session_key IS 'Sensitive: Session key - NEVER expose via API';

-- Block health treatment data
COMMENT ON COLUMN operations_healthvisit.treatment IS 'Sensitive: Medical treatment information - RESTRICTED access';

-- Block card numbers
COMMENT ON COLUMN operations_staffidcard.card_number IS 'Sensitive: ID card number - RESTRICTED access';
COMMENT ON COLUMN operations_studentidcard.card_number IS 'Sensitive: ID card number - RESTRICTED access';

-- ============================================================
-- VERIFICATION: Run this to check RLS status
-- SELECT tablename, rowsecurity 
-- FROM pg_tables 
-- WHERE schemaname = 'public';
-- ============================================================