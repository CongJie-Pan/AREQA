alter table public.messages
  add column if not exists feedback_reason text;

alter table public.messages
  add column if not exists feedback_comment text;

alter table public.messages
  drop constraint if exists messages_feedback_reason_valid;

alter table public.messages
  add constraint messages_feedback_reason_valid
  check (
    feedback_reason is null
    or (
      feedback = 'disliked'
      and feedback_reason in (
        'incorrect_or_incomplete',
        'not_what_i_wanted',
        'slow_or_broken',
        'style_or_tone',
        'safety_or_legal',
        'other'
      )
    )
  );

alter table public.messages
  drop constraint if exists messages_feedback_comment_max_length;

alter table public.messages
  add constraint messages_feedback_comment_max_length
  check (feedback_comment is null or char_length(feedback_comment) <= 2000);
