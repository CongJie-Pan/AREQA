import asyncio
from types import SimpleNamespace

import httpx
import pytest

from backend.services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
)
from backend.services.visual_answer_service import ImageBlock, ImageCandidate, PlannedImageSlot, VisualAnswerService
from backend.services.visual_grounding_agent import VisualBrief, VisualGroundingDecision, VisualTeachingContext


class _FakeRedis:
    """Minimal async Redis double for visual cache read tests."""

    def __init__(self, value):
        self.value = value
        self.closed = False

    async def get(self, key):
        return self.value

    async def aclose(self):
        self.closed = True


class _RecordingHttpClient:
    """Small async HTTP client double that records the last request options."""

    def __init__(self, payload):
        self.payload = payload
        self.last_headers = {}

    async def get(self, url, **kwargs):
        self.last_headers = kwargs.get("headers") or {}
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=self.payload, request=request)


class _RecordingPostClient:
    """Small async HTTP client double that records the last POST request."""

    def __init__(self, payload):
        self.payload = payload
        self.last_url = ""
        self.last_headers = {}
        self.last_json = {}

    async def post(self, url, **kwargs):
        self.last_url = url
        self.last_headers = kwargs.get("headers") or {}
        self.last_json = kwargs.get("json") or {}
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=self.payload, request=request)


class _SequentialPageClient:
    """Async page client double for ordered og:image fallback tests."""

    def __init__(self, responses):
        self.responses = list(responses)

    async def get(self, url):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        request = httpx.Request("GET", url)
        response.request = request
        return response


def _policy(task_intent=TaskIntent.GENERAL_QA):
    """Build a minimal response policy for visual service tests."""

    return ResponsePolicy(
        task_intent=task_intent,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.PLAIN,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        legacy_policy="NORMAL",
    )


def test_should_enrich_for_explain_text_policy():
    """Explain-text turns should allow visual enrichment in v1."""

    service = VisualAnswerService()

    assert service.should_enrich(_policy(TaskIntent.EXPLAIN_TEXT), "請說明森林圖")


def test_should_enrich_for_explicit_visual_request():
    """Explicit visual language should allow enrichment even for general QA."""

    service = VisualAnswerService()

    assert service.should_enrich(_policy(), "請給我一張 diagram")


def test_should_not_enrich_general_non_visual_prompt():
    """General reflective prompts should not trigger image retrieval."""

    service = VisualAnswerService()

    assert service.should_enrich(_policy(), "我在想產品定位") is False


def test_should_attempt_preflight_for_learning_route_policy_fallback():
    """Learning route should still allow visuals when policy classification times out."""

    service = VisualAnswerService()
    turn_plan = SimpleNamespace(route="LEARNING_HELP")

    assert service._should_attempt_preflight(_policy(TaskIntent.GENERAL_QA), "第二次世界大戰歐洲戰場", turn_plan)


def test_cache_key_uses_visual_schema_version():
    """Visual cache keys should invalidate pre-provider placeholder entries."""

    assert VisualAnswerService._cache_key("meta analysis", "diagram").startswith("visual_image:v5:diagram:")


def test_visual_brief_cache_key_uses_preflight_scope():
    """Preflight cache keys should not reuse generic diagram cache entries."""

    brief = VisualBrief(
        visual_type="map",
        search_query="Pacific War map Japanese expansion 1941 1945",
        caption_goal="Show the geography of the Pacific War.",
        reject_if=("document_scan", "book_cover"),
        teaching_context=VisualTeachingContext(
            task_intent="explain_text",
            answer_depth="scaffolded",
            tone="tutoring",
            structure="step_by_step",
            followup_mode="optional",
            legacy_policy="normal",
            turn_route="learning_help",
            turn_reason="learning_help",
        ),
    )

    key = VisualAnswerService._visual_brief_cache_key(brief)
    alternate_context_key = VisualAnswerService._visual_brief_cache_key(
        VisualBrief(
            visual_type=brief.visual_type,
            search_query=brief.search_query,
            caption_goal=brief.caption_goal,
            reject_if=brief.reject_if,
            teaching_context=VisualTeachingContext(
                task_intent="general_qa",
                answer_depth="direct",
                tone="plain",
                structure="short",
                followup_mode="none",
                legacy_policy="normal",
                turn_route="general_chat",
                turn_reason="general_chat",
            ),
        )
    )

    assert key.startswith("visual_image:v5:preflight_map:")
    assert key != VisualAnswerService._cache_key(brief.search_query, "diagram")
    assert key != alternate_context_key


def test_visual_search_query_rewrites_meta_analysis_prompt():
    """Abstract learning prompts should become image-provider metadata queries."""

    query, rule = VisualAnswerService._visual_search_query("什麼是 : meta analysis 統合分析")

    assert query == "meta analysis forest plot diagram"
    assert rule == "meta_analysis_forest_plot"


@pytest.mark.asyncio
async def test_read_cache_rejects_stale_placeholder_image_block(monkeypatch, caplog):
    """Stale placeholder image cache should not render broken cards."""

    caplog.set_level("INFO")
    cached_value = """
    {
      "status": "hit",
      "image_block": {
        "type": "image_block",
        "slotId": "visual-1",
        "topic": "Meta analysis diagram",
        "purpose": "diagram",
        "imageUrl": "https://example.com/meta.png",
        "thumbnailUrl": "https://example.com/meta.png",
        "sourceUrl": "https://example.com/source",
        "sourceDomain": "example.com",
        "caption": "Meta analysis diagram",
        "provider": "wikimedia",
        "license": "unknown",
        "safetyStatus": "pass",
        "matchConfidence": 0.8,
        "heuristicScore": 0.8
      }
    }
    """
    redis = _FakeRedis(cached_value)
    service = VisualAnswerService(redis_factory=lambda *args, **kwargs: redis)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")

    block = await service._read_cache("visual_image:v1:diagram:old", "conversation-1")

    assert block is None
    assert redis.closed is True
    assert "visual.cache_rejected" in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_interleaves_verified_images(monkeypatch, caplog):
    """Resolved images should be interleaved after early paragraphs."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    image = ImageBlock(
        slot_id="visual-1",
        topic="Forest plot",
        purpose="diagram",
        image_url="https://example.com/forest.png",
        thumbnail_url="https://example.com/forest.png",
        source_url="https://example.com/article",
        source_domain="example.com",
        caption="Forest plot example",
        license="unknown",
        safety_status="pass",
        match_confidence=0.6,
    )

    async def fake_search(**kwargs):
        return [{"url": "https://example.com/article"}]

    async def fake_resolve(**kwargs):
        return [image]

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    monkeypatch.setattr(service, "_search_image_sources", fake_search)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段\n\n第二段",
        user_msg="請用圖解說明森林圖",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert [block["type"] for block in blocks] == ["paragraph", "image_block", "paragraph"]
    assert blocks[1]["sourceDomain"] == "example.com"
    assert "visual.slots_planned" in caplog.text
    assert "請用圖解" not in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_uses_planned_image_slot_anchor(monkeypatch, caplog):
    """Model-planned slots should control retrieval query and image placement."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    image = ImageBlock(
        slot_id="visual-1",
        topic="Forest plot",
        purpose="diagram",
        image_url="https://example.com/forest.png",
        thumbnail_url="https://example.com/forest.png",
        source_url="https://example.com/article",
        source_domain="example.com",
        caption="Forest plot example",
        license="unknown",
        safety_status="pass",
        match_confidence=0.8,
    )
    observed = {}

    async def fake_read_cache(cache_key, conversation_id):
        observed["cache_key"] = cache_key
        return None

    async def fake_write_cache(*args, **kwargs):
        return None

    async def fake_resolve(**kwargs):
        observed["visual_query"] = kwargs["visual_query"]
        return [image]

    monkeypatch.setattr(service, "_read_cache", fake_read_cache)
    monkeypatch.setattr(service, "_write_cache", fake_write_cache)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段\n\n第二段",
        user_msg="一般問題不含圖",
        response_policy=_policy(TaskIntent.GENERAL_QA),
        planned_image_slots=[{
            "slot_id": "img_1",
            "query": "forest plot meta analysis example",
            "caption_hint": "用這張圖理解信賴區間與整體效果",
            "anchor_after_paragraph": 1,
        }],
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert [block["type"] for block in blocks] == ["paragraph", "paragraph", "image_block"]
    assert blocks[2]["slotId"] == "img_1"
    assert blocks[2]["explanatoryCaption"] == "用這張圖理解信賴區間與整體效果"
    assert observed["visual_query"] == "forest plot meta analysis example"
    assert "visual.slot_resolution_completed" in caplog.text
    assert "forest plot meta analysis" not in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_omits_unresolved_planned_slot(monkeypatch, caplog):
    """Unresolved planned slots should not emit broken pending image blocks."""

    caplog.set_level("INFO")
    service = VisualAnswerService()

    async def fake_read_cache(*args, **kwargs):
        return None

    async def fake_write_cache(*args, **kwargs):
        return None

    async def fake_resolve(**kwargs):
        return []

    monkeypatch.setattr(service, "_read_cache", fake_read_cache)
    monkeypatch.setattr(service, "_write_cache", fake_write_cache)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段\n\n第二段",
        user_msg="一般問題不含圖",
        response_policy=_policy(TaskIntent.GENERAL_QA),
        planned_image_slots=[{
            "slot_id": "img_1",
            "query": "abstract visual query",
            "caption_hint": "正在找概念圖",
            "anchor_after_paragraph": 0,
        }],
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert blocks == []
    assert "visual.slot_resolution_failed" in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_interleaves_preverified_image_without_query():
    """Preflight images should render from verified id-only markers."""

    service = VisualAnswerService()
    image = ImageBlock(
        slot_id="img_1",
        topic="Pacific War map",
        purpose="diagram",
        image_url="https://upload.wikimedia.org/map.png",
        thumbnail_url="https://upload.wikimedia.org/map-thumb.png",
        source_url="https://commons.wikimedia.org/wiki/File:Pacific_War_Map.png",
        source_domain="commons.wikimedia.org",
        caption="Pacific War map",
        license="CC BY-SA 4.0",
        safety_status="pass",
        match_confidence=0.8,
    )

    blocks = await service.build_answer_blocks(
        answer_text="第一段\n\n第二段",
        user_msg="二戰日本戰況",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        planned_image_slots=[{
            "slot_id": "img_1",
            "anchor_after_paragraph": 0,
        }],
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
        preverified_image_blocks={"img_1": image},
    )

    assert [block["type"] for block in blocks] == ["paragraph", "image_block", "paragraph"]
    assert blocks[1]["slotId"] == "img_1"
    assert blocks[1]["status"] == "resolved"


@pytest.mark.asyncio
async def test_build_answer_blocks_auto_inserts_unused_preverified_image(caplog):
    """Verified preflight images should render even if the model omits markers."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    image = ImageBlock(
        slot_id="img_1",
        topic="Pacific War map",
        purpose="diagram",
        image_url="https://upload.wikimedia.org/map.png",
        thumbnail_url="https://upload.wikimedia.org/map-thumb.png",
        source_url="https://commons.wikimedia.org/wiki/File:Pacific_War_Map.png",
        source_domain="commons.wikimedia.org",
        caption="Pacific War map",
        license="CC BY-SA 4.0",
        safety_status="pass",
        match_confidence=0.8,
    )

    blocks = await service.build_answer_blocks(
        answer_text="第一段\n\n第二段",
        user_msg="二戰日本戰況",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        planned_image_slots=[],
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
        preverified_image_blocks={"img_1": image},
    )

    assert [block["type"] for block in blocks] == ["paragraph", "image_block", "paragraph"]
    assert blocks[1]["slotId"] == "img_1"
    assert "visual.preverified_auto_inserted" in caplog.text


@pytest.mark.asyncio
async def test_prepare_preflight_image_blocks_uses_visual_brief_without_caption_leak(monkeypatch):
    """Preflight should search with the agent brief and avoid internal captions."""

    class _FakeGroundingAgent:
        async def plan(self, **kwargs):
            return VisualBrief(
                visual_type="map",
                search_query="Pacific War map Japanese expansion 1941 1945",
                caption_goal="Show the geography of the Pacific War.",
                reject_if=("document_scan", "book_cover"),
            )

    service = VisualAnswerService()
    service._visual_grounding_agent = _FakeGroundingAgent()
    observed = {}
    image = ImageBlock(
        slot_id="img_1",
        topic="Pacific War map",
        purpose="diagram",
        image_url="https://upload.wikimedia.org/map.png",
        thumbnail_url="https://upload.wikimedia.org/map.png",
        source_url="https://commons.wikimedia.org/wiki/File:Pacific_War_Map.png",
        source_domain="commons.wikimedia.org",
        caption="Pacific War map",
        license="CC BY-SA 4.0",
        safety_status="pass",
        match_confidence=0.8,
    )

    async def fake_resolve_planned(**kwargs):
        slot = kwargs["planned_slots"][0]
        observed["query"] = slot.query
        observed["caption_hint"] = slot.caption_hint
        observed["visual_brief"] = kwargs["visual_brief"]
        return {"img_1": image}

    monkeypatch.setattr(service, "_resolve_planned_image_blocks", fake_resolve_planned)

    blocks = await service.prepare_preflight_image_blocks(
        user_msg="第二次世界大戰日本戰況",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        existing_web_results=None,
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=SimpleNamespace(),
    )

    assert blocks == {"img_1": image}
    assert observed["query"] == "Pacific War map Japanese expansion 1941 1945"
    assert observed["caption_hint"] == ""
    assert observed["visual_brief"].visual_type == "map"


@pytest.mark.asyncio
async def test_resolve_planned_image_blocks_uses_visual_brief_cache_key(monkeypatch, caplog):
    """Preflight slot resolution should bypass stale generic diagram cache."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    brief = VisualBrief(
        visual_type="map",
        search_query="Pacific War map Japanese expansion 1941 1945",
        caption_goal="Show the geography of the Pacific War.",
        reject_if=("document_scan", "book_cover"),
        teaching_context=VisualTeachingContext(
            task_intent="explain_text",
            answer_depth="scaffolded",
            tone="tutoring",
            structure="step_by_step",
            followup_mode="optional",
            legacy_policy="normal",
            turn_route="learning_help",
            turn_reason="learning_help",
        ),
    )
    observed = {}

    async def fake_read_cache(cache_key, conversation_id):
        observed["cache_key"] = cache_key
        return None

    async def fake_write_cache(*args, **kwargs):
        return None

    async def fake_resolve_images(**kwargs):
        observed["allow_og_fallback"] = kwargs["allow_og_fallback"]
        observed["allow_open_provider_fallback"] = kwargs["allow_open_provider_fallback"]
        return []

    monkeypatch.setattr(service, "_read_cache", fake_read_cache)
    monkeypatch.setattr(service, "_write_cache", fake_write_cache)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve_images)

    blocks = await service._resolve_planned_image_blocks(
        planned_slots=[
            PlannedImageSlot(
                slot_id="img_1",
                query=brief.search_query,
                caption_hint="",
                anchor_after_paragraph=0,
            )
        ],
        existing_web_results=None,
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=SimpleNamespace(),
        visual_brief=brief,
    )

    assert blocks == {}
    assert observed["cache_key"] == VisualAnswerService._visual_brief_cache_key(brief)
    assert observed["cache_key"] != VisualAnswerService._cache_key(brief.search_query, "diagram")
    assert observed["allow_og_fallback"] is False
    assert observed["allow_open_provider_fallback"] is True
    assert "visual.cache_scope_selected" in caplog.text
    assert "scope=preflight" in caplog.text
    assert "visual_type=map" in caplog.text


@pytest.mark.asyncio
async def test_preflight_skips_open_provider_and_og_fallback_when_perplexity_fails(monkeypatch, caplog):
    """Preflight should fail fast instead of chaining slower fallback providers."""

    import config as runtime_config

    class _FakeGroundingAgent:
        async def plan(self, **kwargs):
            return VisualBrief(
                visual_type="map",
                search_query="Pacific War map Japanese expansion 1941 1945",
                caption_goal="Show the geography of the Pacific War.",
                reject_if=("document_scan", "book_cover"),
            )

    caplog.set_level("INFO")
    service = VisualAnswerService()
    service._visual_grounding_agent = _FakeGroundingAgent()

    async def no_perplexity_candidates(*args, **kwargs):
        return []

    async def fail_open_provider(*args, **kwargs):
        raise AssertionError("preflight should not query open providers after Perplexity fails")

    async def fail_og_scan(*args, **kwargs):
        raise AssertionError("preflight should not scan og:image fallback")

    monkeypatch.setattr(runtime_config.settings, "enable_perplexity_visual_search", True)
    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight_open_provider_fallback", False)
    monkeypatch.setattr(service, "_query_perplexity_images", no_perplexity_candidates)
    monkeypatch.setattr(service, "_query_wikimedia", fail_open_provider)
    monkeypatch.setattr(service, "_query_openverse", fail_open_provider)
    monkeypatch.setattr(service, "_block_from_result_safe", fail_og_scan)

    blocks = await service.prepare_preflight_image_blocks(
        user_msg="第二次世界大戰日本戰況",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        existing_web_results=[{"url": "https://example.org/article"}],
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=SimpleNamespace(),
    )

    assert blocks == {}
    assert "visual.open_provider_fallback_skipped" in caplog.text
    assert "reason=preflight_budget" in caplog.text


@pytest.mark.asyncio
async def test_preflight_parallel_provider_fallback_uses_open_candidate(monkeypatch, caplog):
    """Preflight should not lose images only because Perplexity is unavailable."""

    import config as runtime_config

    class _FakeGroundingAgent:
        async def plan(self, **kwargs):
            return VisualBrief(
                visual_type="map",
                search_query="World War II European Theater educational labeled map",
                caption_goal="Help the learner connect the explanation to geography.",
                reject_if=("wrong_visual_type", "product_photo", "book_cover"),
            )

        async def evaluate(self, **kwargs):
            return VisualGroundingDecision(
                accepted=True,
                expected_visual_type="map",
                candidate_visual_type="map",
                reason="teaching_goal_match",
            )

    caplog.set_level("INFO")
    service = VisualAnswerService()
    service._visual_grounding_agent = _FakeGroundingAgent()

    async def no_perplexity_candidates(*args, **kwargs):
        return []

    async def wikimedia_candidate(*args, **kwargs):
        return [
            ImageCandidate(
                provider="wikimedia",
                image_url="https://upload.wikimedia.org/europe-map.png",
                thumbnail_url="https://upload.wikimedia.org/europe-map.png",
                source_url="https://commons.wikimedia.org/wiki/File:Europe_Map.png",
                title="World War II European Theater labeled map",
                caption="World War II European Theater labeled map",
                license="Public domain",
                width=1200,
                height=800,
            )
        ]

    async def no_openverse_candidates(*args, **kwargs):
        return []

    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight_parallel_providers", True)
    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight_open_provider_fallback", True)
    monkeypatch.setattr(runtime_config.settings, "enable_perplexity_visual_search", True)
    monkeypatch.setattr(service, "_query_perplexity_images", no_perplexity_candidates)
    monkeypatch.setattr(service, "_query_wikimedia", wikimedia_candidate)
    monkeypatch.setattr(service, "_query_openverse", no_openverse_candidates)

    blocks = await service.prepare_preflight_image_blocks(
        user_msg="請解釋二戰歐洲戰場",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        existing_web_results=None,
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=SimpleNamespace(),
    )

    assert blocks["img_1"].provider == "wikimedia"
    assert "visual.parallel_provider_started" in caplog.text
    assert "visual.parallel_candidates_merged" in caplog.text


@pytest.mark.asyncio
async def test_prepare_preflight_image_blocks_returns_empty_on_timeout(monkeypatch, caplog):
    """Preflight should never block the main answer beyond its configured budget."""

    import config as runtime_config

    class _FakeGroundingAgent:
        async def plan(self, **kwargs):
            return VisualBrief(
                visual_type="diagram",
                search_query="slow visual query",
                caption_goal="Show the concept.",
                reject_if=("decorative",),
            )

    caplog.set_level("INFO")
    service = VisualAnswerService()
    service._visual_grounding_agent = _FakeGroundingAgent()
    monkeypatch.setattr(runtime_config.settings, "visual_preflight_timeout_seconds", 0.01)

    async def slow_resolve_planned(**kwargs):
        await asyncio.sleep(1)
        return {"img_1": object()}

    monkeypatch.setattr(service, "_resolve_planned_image_blocks", slow_resolve_planned)

    blocks = await service.prepare_preflight_image_blocks(
        user_msg="請圖解二戰歐洲戰場",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        existing_web_results=None,
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=SimpleNamespace(),
    )

    assert blocks == {}
    assert "visual.preflight_timeout" in caplog.text
    assert "timeout_seconds=0.1" in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_uses_rewritten_visual_query(monkeypatch, caplog):
    """Visual rewrite should feed cache and providers without logging raw prompts."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    observed = {}

    async def fake_read_cache(cache_key, conversation_id):
        observed["cache_key"] = cache_key
        return None

    async def fake_resolve(**kwargs):
        observed["visual_query"] = kwargs["visual_query"]
        return []

    async def fake_write_cache(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_read_cache", fake_read_cache)
    monkeypatch.setattr(service, "_write_cache", fake_write_cache)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段",
        user_msg="什麼是 : meta analysis 統合分析",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert blocks == []
    assert observed["visual_query"] == "meta analysis forest plot diagram"
    assert observed["cache_key"] == VisualAnswerService._cache_key("meta analysis forest plot diagram", "diagram")
    assert "visual.query_rewritten" in caplog.text
    assert "meta_analysis_forest_plot" in caplog.text
    assert "什麼是" not in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_reuses_existing_web_results(monkeypatch, caplog):
    """WEB_REQUIRED turns should not spend a second external search call."""

    caplog.set_level("INFO")
    service = VisualAnswerService()

    async def fail_search(**kwargs):
        raise AssertionError("existing web results should be reused")

    async def fake_resolve(**kwargs):
        assert kwargs["existing_web_results"] == [{"url": "https://example.com/article"}]
        return [
            ImageBlock(
                slot_id="visual-1",
                topic="Meta analysis",
                purpose="diagram",
                image_url="https://example.com/meta.png",
                thumbnail_url="https://example.com/meta.png",
                source_url="https://example.com/article",
                source_domain="example.com",
                caption="Meta analysis diagram",
                license="unknown",
                safety_status="pass",
                match_confidence=0.6,
            )
        ]

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    monkeypatch.setattr(service, "_search_image_sources", fail_search)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段",
        user_msg="什麼是 meta analysis 統合分析",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=[{"url": "https://example.com/article"}],
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert [block["type"] for block in blocks] == ["paragraph", "image_block"]
    assert "visual.slots_planned" in caplog.text


@pytest.mark.asyncio
async def test_select_image_block_prefers_open_licensed_candidate(caplog):
    """High-scoring Wikimedia candidates should become licensed image blocks."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    block = await service._select_image_block(
        [
            ImageCandidate(
                provider="wikimedia",
                image_url="https://upload.wikimedia.org/example.png",
                thumbnail_url="https://upload.wikimedia.org/thumb.png",
                source_url="https://commons.wikimedia.org/wiki/File:Example.png",
                title="Forest plot diagram",
                caption="Forest plot diagram for meta analysis",
                license="CC BY-SA 4.0",
                license_url="https://creativecommons.org/licenses/by-sa/4.0/",
                creator="Example Creator",
                attribution_string="Example Creator / CC BY-SA 4.0",
                width=900,
                height=500,
            )
        ],
        "forest plot meta analysis diagram",
        "wikimedia",
        "conversation-1",
    )

    assert block is not None
    payload = block.to_frontend()
    assert payload["provider"] == "wikimedia"
    assert payload["license"] == "CC BY-SA 4.0"
    assert payload["creator"] == "Example Creator"
    assert payload["tier"] == "wikimedia"
    assert payload["attributionCaption"] == "Forest plot diagram for meta analysis"
    assert "explanatoryCaption" not in payload
    assert payload["heuristicScore"] >= 0.65
    assert payload["pedagogicalScore"] > 0
    assert "visual.image_selected" in caplog.text
    assert "visual.candidate_top_scored" in caplog.text


@pytest.mark.asyncio
async def test_select_image_block_logs_low_score_candidate_metadata_without_raw_query(caplog):
    """Low-score omissions should expose safe ranking metadata for debugging."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    block = await service._select_image_block(
        [
            ImageCandidate(
                provider="openverse",
                image_url="https://cdn.example.org/image.png",
                thumbnail_url="https://cdn.example.org/thumb.png",
                source_url="https://images.example.org/page",
                title="Unrelated classroom",
                caption="A classroom photo",
                license="cc0",
                width=300,
                height=180,
            )
        ],
        "private raw visual query",
        "openverse",
        "conversation-1",
    )

    assert block is None
    assert "visual.candidate_top_scored" in caplog.text
    assert "top_score=" in caplog.text
    assert "threshold=0.40" in caplog.text
    assert "source_domain=images.example.org" in caplog.text
    assert "dimension_bucket=small" in caplog.text
    assert "private raw visual query" not in caplog.text


@pytest.mark.asyncio
async def test_select_image_block_uses_grounding_agent_to_reject_visual_mismatch(caplog):
    """Grounding should reject a high-score candidate when metadata contradicts intent."""

    class _FakeGroundingAgent:
        async def evaluate(self, *, candidate, **kwargs):
            if "aircraft" in candidate.title.lower():
                return VisualGroundingDecision(
                    accepted=False,
                    expected_visual_type="map",
                    candidate_visual_type="aircraft_photo",
                    reason="visual_type_mismatch",
                )
            return VisualGroundingDecision(
                accepted=True,
                expected_visual_type="map",
                candidate_visual_type="map",
                reason="purpose_match",
            )

    caplog.set_level("INFO")
    service = VisualAnswerService()
    service._visual_grounding_agent = _FakeGroundingAgent()

    block = await service._select_image_block(
        [
            ImageCandidate(
                provider="wikimedia",
                image_url="https://upload.wikimedia.org/aircraft.png",
                thumbnail_url="https://upload.wikimedia.org/aircraft-thumb.png",
                source_url="https://commons.wikimedia.org/wiki/File:Aircraft.png",
                title="World War II aircraft map diagram",
                caption="Aircraft photo with map metadata words",
                license="CC BY 2.0",
                width=900,
                height=500,
            ),
            ImageCandidate(
                provider="wikimedia",
                image_url="https://upload.wikimedia.org/map.png",
                thumbnail_url="https://upload.wikimedia.org/map-thumb.png",
                source_url="https://commons.wikimedia.org/wiki/File:Pacific_War_Map.png",
                title="Pacific War map diagram",
                caption="Map showing Pacific War movement",
                license="CC BY-SA 4.0",
                width=900,
                height=500,
            ),
        ],
        "World War II Pacific War map diagram",
        "wikimedia",
        "conversation-1",
        "Show a map that helps explain World War II geography.",
        SimpleNamespace(),
    )

    assert block is not None
    assert block.image_url == "https://upload.wikimedia.org/map-thumb.png"
    assert block.source_domain == "commons.wikimedia.org"
    assert "visual.candidate_rejected" in caplog.text
    assert "candidate_type=aircraft_photo" in caplog.text


@pytest.mark.asyncio
async def test_select_image_block_rejects_preflight_candidate_when_grounding_unavailable(caplog):
    """Preflight should not display candidates that could not be grounded."""

    class _UnavailableGroundingAgent:
        async def evaluate(self, *, candidate, **kwargs):
            return VisualGroundingDecision(
                accepted=True,
                expected_visual_type="unknown",
                candidate_visual_type="unknown",
                reason="model_unavailable",
            )

    caplog.set_level("INFO")
    service = VisualAnswerService()
    service._visual_grounding_agent = _UnavailableGroundingAgent()
    brief = VisualBrief(
        visual_type="map",
        search_query="Pacific War map Japanese expansion 1941 1945",
        caption_goal="Show the geography of the Pacific War.",
        reject_if=("document_scan", "book_cover"),
        teaching_context=VisualTeachingContext(
            task_intent="explain_text",
            answer_depth="scaffolded",
            tone="tutoring",
            structure="step_by_step",
            followup_mode="optional",
            legacy_policy="normal",
            turn_route="learning_help",
            turn_reason="learning_help",
        ),
    )

    block = await service._select_image_block(
        [
            ImageCandidate(
                provider="perplexity_images",
                image_url="https://cdn.example.org/pacific-map.jpg",
                thumbnail_url="https://cdn.example.org/pacific-map.jpg",
                source_url="https://example.org/pacific-war-map",
                title="Pacific War map diagram",
                caption="Pacific War map diagram",
                license="unknown",
                width=1200,
                height=800,
            )
        ],
        "Pacific War map diagram",
        "perplexity_images",
        "conversation-1",
        "Show a map that helps explain World War II geography.",
        SimpleNamespace(),
        brief,
    )

    assert block is None
    assert "visual.candidate_rejected" in caplog.text
    assert "grounding_model_unavailable" in caplog.text


def test_image_block_debug_log_respects_config(monkeypatch, caplog):
    """Image block diagnostics should be controlled by config settings."""

    import config as runtime_config

    caplog.set_level("INFO")
    block = ImageBlock(
        slot_id="visual-1",
        topic="Forest plot",
        purpose="diagram",
        image_url="https://upload.wikimedia.org/example.png",
        thumbnail_url="https://upload.wikimedia.org/thumb.png",
        source_url="https://commons.wikimedia.org/wiki/File:Example.png",
        source_domain="commons.wikimedia.org",
        caption="Forest plot",
        provider="wikimedia",
        license="CC BY-SA 4.0",
        safety_status="pass",
        match_confidence=0.8,
        explanatory_caption="caption",
        pedagogical_score=0.7,
    )

    monkeypatch.setattr(runtime_config.settings, "enable_visual_answer_debug_logs", False)
    VisualAnswerService._log_image_block_selected("conversation-1", block, "test")
    assert "visual.image_block_ready" not in caplog.text

    monkeypatch.setattr(runtime_config.settings, "enable_visual_answer_debug_logs", True)
    VisualAnswerService._log_image_block_selected("conversation-1", block, "test")
    assert "visual.image_block_ready" in caplog.text
    assert "source_domain=commons.wikimedia.org" in caplog.text


@pytest.mark.asyncio
async def test_wikimedia_request_uses_configured_user_agent(monkeypatch):
    """Wikimedia requests should identify AREQA with a stable User-Agent."""

    import config as runtime_config

    service = VisualAnswerService()
    client = _RecordingHttpClient({"query": {"pages": {}}})
    monkeypatch.setattr(runtime_config.settings, "areqa_visual_user_agent", "AREQA-Test/1.0")

    await service._query_wikimedia(client, "meta analysis", "conversation-1")

    assert client.last_headers["User-Agent"] == "AREQA-Test/1.0"


@pytest.mark.asyncio
async def test_openverse_request_uses_optional_access_token(monkeypatch):
    """Openverse requests should use an optional bearer token when configured."""

    import config as runtime_config

    service = VisualAnswerService()
    client = _RecordingHttpClient({"results": []})
    monkeypatch.setattr(runtime_config.settings, "areqa_visual_user_agent", "AREQA-Test/1.0")
    monkeypatch.setenv("OPENVERSE_ACCESS_TOKEN", "openverse-token")

    await service._query_openverse(client, "meta analysis", "conversation-1")

    assert client.last_headers["User-Agent"] == "AREQA-Test/1.0"
    assert client.last_headers["Authorization"] == "Bearer openverse-token"


@pytest.mark.asyncio
async def test_perplexity_image_request_uses_sonar_return_images(monkeypatch):
    """Perplexity image provider should request structured Sonar image results."""

    import config as runtime_config

    service = VisualAnswerService()
    client = _RecordingPostClient(
        {
            "images": [
                {
                    "image_url": "https://cdn.example.org/pacific-map.jpg",
                    "origin_url": "https://example.org/pacific-war-map",
                    "title": "Pacific War map",
                    "width": 1200,
                    "height": 800,
                }
            ]
        }
    )
    brief = VisualBrief(
        visual_type="map",
        search_query="Pacific War map Japanese expansion 1941 1945",
        caption_goal="Show the geography of the Pacific War.",
        reject_if=("document_scan", "book_cover"),
        teaching_context=VisualTeachingContext(
            task_intent="explain_text",
            answer_depth="scaffolded",
            tone="tutoring",
            structure="step_by_step",
            followup_mode="optional",
            legacy_policy="normal",
            turn_route="learning_help",
            turn_reason="learning_help",
        ),
    )
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-token")
    monkeypatch.setattr(runtime_config.settings, "perplexity_sonar_api_url", "https://api.perplexity.ai/v1/sonar")
    monkeypatch.setattr(runtime_config.settings, "perplexity_visual_search_model", "sonar")

    candidates = await service._query_perplexity_images(
        client,
        "Pacific War map Japanese expansion 1941 1945",
        "conversation-1",
        brief,
    )

    assert client.last_url == "https://api.perplexity.ai/v1/sonar"
    assert client.last_headers["Authorization"] == "Bearer pplx-token"
    assert client.last_json["model"] == "sonar"
    assert client.last_json["return_images"] is True
    assert client.last_json["num_images"] >= 4
    assert client.last_json["messages"][1]["content"].find('"task_intent": "explain_text"') >= 0
    assert client.last_json["messages"][1]["content"].find('"answer_depth": "scaffolded"') >= 0
    assert client.last_json["messages"][1]["content"].find("shopping pages") >= 0
    assert candidates[0].provider == "perplexity_images"
    assert candidates[0].image_url == "https://cdn.example.org/pacific-map.jpg"
    assert candidates[0].source_url == "https://example.org/pacific-war-map"
    assert candidates[0].width == 1200


@pytest.mark.asyncio
async def test_resolve_images_prefers_perplexity_image_provider(monkeypatch, caplog):
    """Perplexity image candidates should run before Wikimedia/Openverse fallbacks."""

    import config as runtime_config

    caplog.set_level("INFO")
    service = VisualAnswerService()
    monkeypatch.setattr(runtime_config.settings, "enable_perplexity_visual_search", True)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-token")

    async def perplexity_candidate(client, query, conversation_id, visual_brief=None):
        return [
            ImageCandidate(
                provider="perplexity_images",
                image_url="https://cdn.example.org/pacific-map.jpg",
                thumbnail_url="https://cdn.example.org/pacific-map.jpg",
                source_url="https://example.org/pacific-war-map",
                title="Pacific War map diagram",
                caption="Pacific War map diagram",
                license="unknown",
                width=1200,
                height=800,
            )
        ]

    async def fail_wikimedia(*args, **kwargs):
        raise AssertionError("Wikimedia should not run when Perplexity returns a selected image")

    monkeypatch.setattr(service, "_query_perplexity_images", perplexity_candidate)
    monkeypatch.setattr(service, "_query_wikimedia", fail_wikimedia)

    blocks = await service._resolve_images(
        user_msg="第二次世界大戰日本戰況",
        visual_query="Pacific War map diagram",
        existing_web_results=None,
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert len(blocks) == 1
    assert blocks[0].provider == "perplexity_images"
    assert blocks[0].image_url == "https://cdn.example.org/pacific-map.jpg"
    assert "stage=perplexity_images" in caplog.text


@pytest.mark.asyncio
async def test_resolve_images_continues_after_provider_http_error(monkeypatch, caplog):
    """Provider failure should fall through to the next image source."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    calls = []

    async def fail_wikimedia(client, query, conversation_id):
        calls.append("wikimedia")
        request = httpx.Request("GET", "https://commons.wikimedia.org/w/api.php")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    async def openverse_candidate(client, query, conversation_id):
        calls.append("openverse")
        return [
            ImageCandidate(
                provider="openverse",
                image_url="https://images.openverse.org/meta-analysis.png",
                thumbnail_url="https://images.openverse.org/meta-analysis-thumb.png",
                source_url="https://openverse.org/image/meta-analysis",
                title="Meta analysis forest plot diagram",
                caption="Meta analysis forest plot diagram",
                license="cc0",
                width=900,
                height=500,
            )
        ]

    monkeypatch.setattr(service, "_query_wikimedia", fail_wikimedia)
    monkeypatch.setattr(service, "_query_openverse", openverse_candidate)

    blocks = await service._resolve_images(
        user_msg="meta analysis forest plot diagram",
        existing_web_results=None,
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert calls == ["wikimedia", "openverse"]
    assert len(blocks) == 1
    assert blocks[0].provider == "openverse"
    assert "visual.provider_failed" in caplog.text
    assert "HTTPStatusError" in caplog.text
    assert "status_code=429" in caplog.text


@pytest.mark.asyncio
async def test_wikimedia_debug_logs_include_safe_http_metadata(monkeypatch, caplog):
    """Detailed Wikimedia failure logs should be opt-in and privacy-preserving."""

    import config as runtime_config

    caplog.set_level("INFO")
    service = VisualAnswerService()

    async def fail_wikimedia(client, query, conversation_id):
        request = httpx.Request("GET", "https://commons.wikimedia.org/w/api.php")
        response = httpx.Response(
            403,
            json={"error": {"code": "badaccess"}},
            headers={"content-type": "application/json", "retry-after": "30"},
            request=request,
        )
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    async def no_openverse_candidates(client, query, conversation_id):
        return []

    monkeypatch.setattr(runtime_config.settings, "wikimedia_image_debug_logs", True)
    monkeypatch.setattr(service, "_query_wikimedia", fail_wikimedia)
    monkeypatch.setattr(service, "_query_openverse", no_openverse_candidates)

    await service._resolve_images(
        user_msg="private raw query should not be logged",
        existing_web_results=[],
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert "visual.wikimedia_failed_debug" in caplog.text
    assert "status_code=403" in caplog.text
    assert "retry_after=30" in caplog.text
    assert "wiki_error_code=badaccess" in caplog.text
    assert "private raw query" not in caplog.text


@pytest.mark.asyncio
async def test_og_image_fallback_continues_after_page_timeout(caplog):
    """One slow web result should not abort remaining og:image candidates."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    timeout_request = httpx.Request("GET", "https://slow.example.org/article")
    client = _SequentialPageClient(
        [
            httpx.ConnectTimeout("connection timed out", request=timeout_request),
            httpx.Response(
                200,
                text='<html><head><meta property="og:image" content="https://cdn.example.org/meta.png"><title>Meta Analysis</title></head></html>',
            ),
        ]
    )

    first = await service._block_from_result_safe(
        client,
        {"url": "https://slow.example.org/article", "title": "Slow result"},
        1,
        "conversation-1",
    )
    second = await service._block_from_result_safe(
        client,
        {"url": "https://source.example.org/article", "title": "Meta Analysis"},
        1,
        "conversation-1",
    )

    assert first is None
    assert second is not None
    assert second.image_url == "https://cdn.example.org/meta.png"
    assert "visual.og_image_failed" in caplog.text
    assert "source_domain=slow.example.org" in caplog.text
    assert "ConnectTimeout" in caplog.text


@pytest.mark.asyncio
async def test_build_answer_blocks_uses_positive_cache(monkeypatch, caplog):
    """Positive Redis cache hits should skip all providers."""

    caplog.set_level("INFO")
    service = VisualAnswerService()

    async def fake_read_cache(cache_key, conversation_id):
        return {
            "type": "image_block",
            "slotId": "visual-1",
            "topic": "Cached image",
            "purpose": "diagram",
            "imageUrl": "https://example.com/cached.png",
            "thumbnailUrl": "https://example.com/cached.png",
            "sourceUrl": "https://example.com/source",
            "sourceDomain": "example.com",
            "caption": "Cached image",
            "provider": "wikimedia",
            "license": "CC0",
            "safetyStatus": "pass",
            "matchConfidence": 0.8,
            "heuristicScore": 0.8,
        }

    async def fail_resolve(**kwargs):
        raise AssertionError("providers should not run on positive cache hit")

    monkeypatch.setattr(service, "_read_cache", fake_read_cache)
    monkeypatch.setattr(service, "_resolve_images", fail_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段",
        user_msg="請解釋 meta analysis",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert [block["type"] for block in blocks] == ["paragraph", "image_block"]
    assert blocks[1]["provider"] == "wikimedia"


@pytest.mark.asyncio
async def test_build_answer_blocks_uses_negative_cache(monkeypatch):
    """Negative cache hits should skip provider calls and omit image blocks."""

    service = VisualAnswerService()

    async def fake_read_cache(cache_key, conversation_id):
        return {"status": "negative"}

    async def fail_resolve(**kwargs):
        raise AssertionError("providers should not run on negative cache hit")

    monkeypatch.setattr(service, "_read_cache", fake_read_cache)
    monkeypatch.setattr(service, "_resolve_images", fail_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段",
        user_msg="請解釋 meta analysis",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        existing_web_results=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert blocks == []
