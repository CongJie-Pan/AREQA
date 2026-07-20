create or replace view public.feedback_submissions_taipei as
select
  id,
  user_id,
  email,
  display_name,
  content,
  page_path,
  user_agent,
  status,
  created_at,
  created_at at time zone 'Asia/Taipei' as created_at_taipei
from public.feedback_submissions;
