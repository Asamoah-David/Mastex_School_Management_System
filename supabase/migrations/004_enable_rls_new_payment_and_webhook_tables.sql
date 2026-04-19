-- Enable RLS on newly introduced public tables flagged by Supabase linter.
-- This keeps PostgREST exposure locked down by default (no explicit policies).

ALTER TABLE IF EXISTS public.finance_paymenttransaction ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.integrations_webhookdeliveryattempt ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.finance_subscriptionpayment ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.operations_hostelfeepayment ENABLE ROW LEVEL SECURITY;
