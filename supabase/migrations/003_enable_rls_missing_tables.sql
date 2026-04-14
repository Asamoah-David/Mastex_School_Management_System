-- Enable RLS on missing tables
-- Fixes Supabase security linter errors: rls_disabled_in_public

-- ==================================================
-- 1. integrations_schoolwebhookendpoint
-- ==================================================
ALTER TABLE public.integrations_schoolwebhookendpoint ENABLE ROW LEVEL SECURITY;

-- Webhook endpoints are for internal service use only
-- No public access, only authenticated users with admin permissions
CREATE POLICY "School admins can manage webhook endpoints" 
ON public.integrations_schoolwebhookendpoint
FOR ALL 
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.accounts_user u
    WHERE u.id = (auth.uid())::text::bigint
    AND (u.role = 'school_admin' OR u.is_superuser = true)
    AND u.school_id = public.integrations_schoolwebhookendpoint.school_id
  )
);

-- ==================================================
-- 2. academics_gradepoint
-- ==================================================
ALTER TABLE public.academics_gradepoint ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read grade points
CREATE POLICY "Authenticated users can read grade points" 
ON public.academics_gradepoint
FOR SELECT
TO authenticated
USING (true);

-- Only school admins can write grade points
CREATE POLICY "School admins can manage grade points" 
ON public.academics_gradepoint
FOR ALL
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.accounts_user u
    WHERE u.id = (auth.uid())::text::bigint
    AND (u.role = 'school_admin' OR u.is_superuser = true)
  )
);

-- ==================================================
-- 3. academics_studentresultsummary
-- ==================================================
ALTER TABLE public.academics_studentresultsummary ENABLE ROW LEVEL SECURITY;

-- Users can see results for their school
CREATE POLICY "Users can read result summaries for their school" 
ON public.academics_studentresultsummary
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 
    FROM public.accounts_user u
    JOIN public.students_student s ON s.id = public.academics_studentresultsummary.student_id
    WHERE u.id = (auth.uid())::text::bigint
    AND u.school_id = s.school_id
  )
);

-- Only school admins and teachers can manage summaries
CREATE POLICY "Admins and teachers can manage result summaries" 
ON public.academics_studentresultsummary
FOR ALL
TO authenticated
USING (
  EXISTS (
    SELECT 1 
    FROM public.accounts_user u
    JOIN public.students_student s ON s.id = public.academics_studentresultsummary.student_id
    WHERE u.id = (auth.uid())::text::bigint
    AND (u.role IN ('school_admin', 'teacher') OR u.is_superuser = true)
    AND u.school_id = s.school_id
  )
);

-- ==================================================
-- 4. Storage policies skipped (run manually in Supabase dashboard)
-- ==================================================
-- Storage policies are best configured through Supabase UI
-- These lines are commented out to avoid system table issues
-- You can apply storage policies manually in the Supabase Storage dashboard
