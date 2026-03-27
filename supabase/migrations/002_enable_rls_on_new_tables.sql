-- Enable Row Level Security (RLS) on tables that were missing RLS
-- Note: Policies not added because Django handles authentication, not Supabase auth
-- RLS will be bypassed for the Django app's database connection

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
