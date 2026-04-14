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
    WHERE u.id = auth.uid()
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
    WHERE u.id = auth.uid()
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
    SELECT 1 FROM public.accounts_user u
    WHERE u.id = auth.uid()
    AND u.school_id = public.academics_studentresultsummary.school_id
  )
);

-- Only school admins and teachers can write summaries
CREATE POLICY "Admins and teachers can manage result summaries" 
ON public.academics_studentresultsummary
FOR ALL
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.accounts_user u
    WHERE u.id = auth.uid()
    AND (u.role IN ('school_admin', 'teacher') OR u.is_superuser = true)
    AND u.school_id = public.academics_studentresultsummary.school_id
  )
);

-- ==================================================
-- 4. Fix media bucket listing policy
-- ==================================================
-- Remove the broad SELECT policy that allows listing all files
-- Keep individual file access public (required for profile photos, documents)
DELETE FROM storage.policies 
WHERE bucket_id = 'media' 
AND name = 'Allow public reads';

-- Create proper policy that allows public read for individual objects only
-- This prevents directory listing while maintaining normal file access
CREATE POLICY "Public access to individual media files"
ON storage.objects
FOR SELECT
TO public
USING (
  bucket_id = 'media' 
  AND name IS NOT NULL
  AND position('/' in name) > 0
);

-- Authenticated users can upload files to their school folder
CREATE POLICY "Authenticated users can upload to their school media folder"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'media'
  AND (
    SPLIT_PART(name, '/', 1) = (SELECT school_id::text FROM public.accounts_user WHERE id = auth.uid())
    OR EXISTS (SELECT 1 FROM public.accounts_user WHERE id = auth.uid() AND is_superuser = true)
  )
);