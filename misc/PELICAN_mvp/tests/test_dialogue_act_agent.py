from pelican_mvp.agents import AgentExecutionContext, DialogueActAgent
from pelican_mvp.models import LearnerDialogueAct


def test_dialogue_act_agent_detects_micro_check_term_question_without_raw_payload() -> None:
    agent = DialogueActAgent()

    interpretation = agent.classify(
        "什麼轉折點？",
        previous_tutor_message="先不用完整重述。你可以先說說看最關鍵的轉折點是哪一個？",
        node_label="中途島戰役的戰略轉折",
        context=AgentExecutionContext(turn_id="turn_safe"),
    )

    metadata = interpretation.result.to_safe_metadata()
    assert interpretation.signal.act is LearnerDialogueAct.MICRO_CHECK_CONFUSION
    assert interpretation.signal.target_text == "轉折點"
    assert interpretation.signal.reason_code == "short_term_question"
    assert metadata["role"] == "dialogue_act_agent"
    assert metadata["artifact_type"] == "dialogue_act_signal"
    assert "什麼轉折點" not in metadata["display_summary"]


def test_dialogue_act_agent_detects_term_definition_request() -> None:
    agent = DialogueActAgent()

    interpretation = agent.classify("戰略主動權是什麼？")

    assert interpretation.signal.act is LearnerDialogueAct.TERM_DEFINITION_REQUEST
    assert interpretation.signal.target_text == "戰略主動權"


def test_dialogue_act_agent_detects_micro_check_choice_confusion() -> None:
    agent = DialogueActAgent()

    interpretation = agent.classify(
        "我不知道要選哪個",
        previous_tutor_message="可以從原因、轉折點、影響裡先選一個。",
    )

    assert interpretation.signal.act is LearnerDialogueAct.MICRO_CHECK_CONFUSION
    assert interpretation.signal.reason_code == "micro_check_choice_confusion"


def test_dialogue_act_agent_defaults_content_to_answer_attempt() -> None:
    agent = DialogueActAgent()

    interpretation = agent.classify("我覺得是因為日軍航空母艦損失太大")

    assert interpretation.signal.act is LearnerDialogueAct.ANSWER_ATTEMPT
    assert interpretation.signal.reason_code == "default_answer_attempt"
