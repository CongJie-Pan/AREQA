(.venv) @CongJie-Pan ➜ /workspaces/AREQA/misc/PELICAN_mvp (master) $ python -m pelican_mvp
INFO:     Started server process [106362]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:46790 - "GET / HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=tutoring activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_api_start phase=tutoring activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:46790 - "POST /api/start HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=tutoring activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_intake_progress phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_api_reset phase=onboarding activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:46790 - "POST /api/reset HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=intake_topic status=done detail=topic_received skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=domain_resolved status=done detail=humanities:matched_topic_alias skill=- node=-
PELICAN INFO pelican_intake_progress phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_api_response phase=onboarding activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:46806 - "POST /api/respond HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_intake_progress phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_api_reset phase=onboarding activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:60900 - "POST /api/reset HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=intake_topic status=done detail=topic_received skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=domain_resolved status=done detail=stem:matched_topic_alias skill=- node=-
PELICAN INFO pelican_intake_progress phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_api_response phase=onboarding activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:60900 - "POST /api/respond HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=intent_detected status=done detail=conceptual skill=- node=-
PELICAN INFO pelican_intake_progress phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_api_response phase=onboarding activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:50404 - "POST /api/respond HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=onboarding activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=level_detected status=done detail=advanced skill=- node=-
PELICAN INFO pelican_skill_route_selected phase=- activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_skill_loaded phase=- activity=- status=- detail=- skill=deep_learning node=-
PELICAN INFO pelican_skill_compiled phase=- activity=- status=- detail=- skill=deep_learning node=-
PELICAN INFO pelican_plan_generated phase=- activity=- status=- detail=- skill=deep_learning node=-
PELICAN INFO pelican_activity phase=onboarding activity=skill_loaded status=done detail=deep_learning skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=skill_validated status=done detail=validated_generated skill=- node=-
PELICAN INFO pelican_activity phase=onboarding activity=plan_compiled status=done detail=1 nodes skill=- node=-
PELICAN INFO pelican_phase_transition phase=diagnosis activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=diagnosis activity=diagnostic_selected status=done detail=skill:math_intuition skill=deep_learning node=math_intuition
PELICAN INFO pelican_api_response phase=diagnosis activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:49776 - "POST /api/respond HTTP/1.1" 200 OK
PELICAN INFO pelican_state_loaded phase=diagnosis activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=diagnosis activity=response_classified status=done detail=incorrect skill=deep_learning node=math_intuition
PELICAN INFO pelican_activity phase=diagnosis activity=evidence_applied status=done detail=math_intuition skill=deep_learning node=math_intuition
PELICAN INFO pelican_memory_updated phase=- activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=diagnosis activity=memory_updated status=done detail=incorrect skill=deep_learning node=math_intuition
PELICAN INFO pelican_edf_evaluated phase=- activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=diagnosis activity=edf_evaluated status=done detail=probe_understanding skill=deep_learning node=math_intuition
PELICAN INFO pelican_diagnosis_updated phase=- activity=- status=- detail=- skill=- node=-
PELICAN INFO pelican_activity phase=diagnosis activity=remediation_selected status=done detail=math_intuition skill=deep_learning node=math_intuition
PELICAN INFO pelican_api_response phase=tutoring activity=- status=- detail=- skill=- node=-
INFO:     127.0.0.1:47932 - "POST /api/respond HTTP/1.1" 200 OK