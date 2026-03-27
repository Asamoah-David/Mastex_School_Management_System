-- Enable Row Level Security (RLS) on tables that were missing RLS
-- These tables were created in migration 0008_grading_system_models

-- Enable RLS on academics tables
ALTER TABLE public.academics_assessmenttype ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.academics_gradingpolicy ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.academics_gradepoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.academics_assessmentscore ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.academics_examscore ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.academics_studentresultsummary ENABLE ROW LEVEL SECURITY;

-- Enable RLS on finance table
ALTER TABLE public.finance_feepayment ENABLE ROW LEVEL SECURITY;

-- Enable RLS on notifications table
ALTER TABLE public.notifications_notification ENABLE ROW LEVEL SECURITY;

-- Create RLS policies to allow authenticated users to access their school's data
-- For academics tables (filter by school_id)

-- Assessment Type - allow access to school users
CREATE POLICY "School users can view assessment types" ON public.academics_assessmenttype
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Grading Policy - allow access to school users
CREATE POLICY "School users can view grading policies" ON public.academics_gradingpolicy
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Grade Point - allow access to school users
CREATE POLICY "School users can view grade points" ON public.academics_gradepoint
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Assessment Score - allow access to school users
CREATE POLICY "School users can view assessment scores" ON public.academics_assessmentscore
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Exam Score - allow access to school users  
CREATE POLICY "School users can view exam scores" ON public.academics_examscore
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Student Result Summary - allow access to school users
CREATE POLICY "School users can view result summaries" ON public.academics_studentresultsummary
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Fee Payment - allow access to school users
CREATE POLICY "School users can view fee payments" ON public.finance_feepayment
    FOR SELECT USING (school_id IN (SELECT school_id FROM auth.users WHERE id = auth.uid()));

-- Notification - allow users to see their own notifications
CREATE POLICY "Users can view own notifications" ON public.notifications_notification
    FOR SELECT USING (user_id = auth.uid());