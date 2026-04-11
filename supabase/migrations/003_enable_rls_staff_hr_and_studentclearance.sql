-- RLS for HR and student clearance tables (Supabase linter 0013_rls_disabled_in_public).
-- Matches pattern in 001_enable_rls_security.sql: enable RLS + service_role bypass for PostgREST.

ALTER TABLE public.accounts_staffpayrollpayment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accounts_staffcontract ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accounts_staffrolechangelog ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accounts_staffteachingassignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.students_studentclearance ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_bypass_accounts_staffpayrollpayment"
  ON public.accounts_staffpayrollpayment FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_accounts_staffcontract"
  ON public.accounts_staffcontract FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_accounts_staffrolechangelog"
  ON public.accounts_staffrolechangelog FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_accounts_staffteachingassignment"
  ON public.accounts_staffteachingassignment FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_bypass_students_studentclearance"
  ON public.students_studentclearance FOR ALL TO service_role USING (true) WITH CHECK (true);
