"""Public data contracts for visual answer enrichment.

The classes in this module are imported by multiple backend services and are
re-exported from ``visual_answer_service`` for backward compatibility. Their
frontend wire shapes, defaults, and cache restoration semantics are stable
contracts and should not change without coordinated API and frontend tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class VisualPreflightDecision:
    """Privacy-safe decision metadata for visual preflight cost gating.

    Args:
        allowed: Whether provider lookup or PDF rendering may run this turn.
        blocking_allowed: Whether provider lookup or PDF rendering may block
            the first text token. Only hard visual requirements should set this
            to true; optional visual enrichment must not extend TTFT.
        trigger: Stable reason bucket that made the gate allow or deny work.
        visual_support: EDF response-policy visual support enum value.
        visual_reason: EDF response-policy visual reason enum value.
        explicit_visual_request: Whether the user explicitly asked for visual
            output using a bounded keyword allowlist.
        known_visual_affordance: Whether a deterministic educational affordance
            matched a graph-heavy concept.
        max_images: Effective service image cap.

    Side Effects:
        None. Callers own structured logging so they can add request-scoped
        correlation fields without passing raw user text into log metadata.
    """

    allowed: bool
    blocking_allowed: bool
    trigger: str
    visual_support: str
    visual_reason: str
    explicit_visual_request: bool
    known_visual_affordance: bool
    max_images: int


@dataclass(frozen=True, slots=True)
class ImageBlock:
    """Verified image display metadata for the frontend.

    Args:
        slot_id: Stable per-answer slot identifier.
        topic: Short display topic derived from the source title or query.
        purpose: Visual purpose used by the frontend for future styling.
        image_url: Direct image URL resolved from source page metadata.
        thumbnail_url: Optional thumbnail URL. Defaults to the direct image.
        source_url: Source page URL used for attribution and click-through.
        source_domain: Safe display domain extracted from source_url.
        caption: User-visible caption.
        provider: Source provider that produced the image.
        license: Best-effort license label.
        license_url: Optional provider license URL.
        creator: Optional creator/author display string.
        attribution_string: Optional attribution required by the provider.
        attribution_caption: Short factual caption shown near attribution.
        explanatory_caption: Pedagogical caption tied to the visible image.
        width: Optional image width.
        height: Optional image height.
        safety_status: Backend safety gate result.
        match_confidence: Conservative confidence score from metadata matching.
        heuristic_score: Cheap metadata-only relevance score.
        pedagogical_score: Cheap instructional usefulness score.
        vision_summary: Optional vision-model summary of visible content.
        visible_elements: Optional bounded list of visible image elements.
        how_to_read: Optional ordered reading guidance from the vision model.
        vision_confidence: Optional confidence label from the vision model.
        vision_limitations: Optional bounded uncertainty notes.
        vision_source: Stable source label for image-understanding metadata.
        cache_key: Internal cache key that may be committed only after output
            understanding succeeds. This field is intentionally not serialized
            to the frontend.
        cache_ttl_seconds: Internal positive-cache TTL paired with cache_key.
        alternative_blocks: Internal fallback image blocks for the same planned
            slot. These are attempted when the initially selected image cannot
            be downloaded or understood.
        storage_bucket: Optional Supabase Storage bucket for persisted
            attachment-derived images.
        storage_path: Optional Supabase Storage object path for persisted
            attachment-derived images.
        storage_expires_at: Unix timestamp when a signed image URL expires.
        placement_section: Backend-only paper section where this verified image
            should be placed by the main answer model.
        planner_hint: Backend-only planner rationale. This is prompt inventory
            material only and is intentionally not serialized to the frontend.
        transient: Whether the block contains request-scoped attachment pixels
            that clients must not write to durable stores.
    """

    slot_id: str
    topic: str
    purpose: str
    image_url: str
    thumbnail_url: str
    source_url: str
    source_domain: str
    caption: str
    provider: str = "og_image"
    license: str = "unknown"
    license_url: str = ""
    creator: str = ""
    attribution_string: str = ""
    attribution_caption: str = ""
    explanatory_caption: str = ""
    width: int | None = None
    height: int | None = None
    safety_status: str = "pass"
    match_confidence: float = 0.0
    heuristic_score: float = 0.0
    pedagogical_score: float = 0.0
    vision_summary: str = ""
    visible_elements: tuple[str, ...] = ()
    how_to_read: tuple[str, ...] = ()
    vision_confidence: str = "unknown"
    vision_limitations: tuple[str, ...] = ()
    vision_source: str = "unavailable"
    cache_key: str = ""
    cache_ttl_seconds: int = 0
    alternative_blocks: tuple["ImageBlock", ...] = ()
    storage_bucket: str = ""
    storage_path: str = ""
    storage_expires_at: int | None = None
    placement_section: str = ""
    planner_hint: str = ""
    transient: bool = False

    def to_frontend(self) -> dict[str, Any]:
        """Return the camelCase wire shape consumed by the frontend."""

        payload: dict[str, Any] = {
            "type": "image_block",
            "slotId": self.slot_id,
            "topic": self.topic,
            "purpose": self.purpose,
            "imageUrl": self.image_url,
            "thumbnailUrl": self.thumbnail_url,
            "sourceUrl": self.source_url,
            "sourceDomain": self.source_domain,
            "caption": self.caption,
            "provider": self.provider,
            "tier": self.provider,
            "license": self.license,
            "status": "resolved",
            "safetyStatus": self.safety_status,
            "matchConfidence": self.match_confidence,
            "heuristicScore": self.heuristic_score,
            "pedagogicalScore": self.pedagogical_score,
        }
        if self.attribution_caption:
            payload["attributionCaption"] = self.attribution_caption
        if self.explanatory_caption:
            payload["explanatoryCaption"] = self.explanatory_caption
        if self.license_url:
            payload["licenseUrl"] = self.license_url
        if self.creator:
            payload["creator"] = self.creator
        if self.attribution_string:
            payload["attributionString"] = self.attribution_string
        if self.vision_summary:
            payload["visionSummary"] = self.vision_summary
        if self.visible_elements:
            payload["visibleElements"] = list(self.visible_elements)
        if self.how_to_read:
            payload["howToRead"] = list(self.how_to_read)
        if self.vision_confidence and self.vision_confidence != "unknown":
            payload["visionConfidence"] = self.vision_confidence
        if self.vision_limitations:
            payload["visionLimitations"] = list(self.vision_limitations)
        if self.vision_source and self.vision_source != "unavailable":
            payload["visionSource"] = self.vision_source
        if self.storage_bucket:
            payload["storageBucket"] = self.storage_bucket
        if self.storage_path:
            payload["storagePath"] = self.storage_path
        if self.storage_expires_at is not None:
            payload["storageExpiresAt"] = self.storage_expires_at
        if self.transient:
            payload["transient"] = True
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        return payload


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    """Provider-normalized image candidate before final ranking.

    Args:
        provider: Candidate provider identifier.
        image_url: Direct image URL.
        thumbnail_url: Thumbnail URL for card rendering.
        source_url: Attribution/click-through URL.
        title: Candidate title.
        caption: Candidate caption or description.
        license: Provider license label.
        license_url: Optional license URL.
        creator: Optional creator/author.
        attribution_string: Optional attribution text.
        width: Optional width.
        height: Optional height.
    """

    provider: str
    image_url: str
    thumbnail_url: str
    source_url: str
    title: str
    caption: str
    license: str
    license_url: str = ""
    creator: str = ""
    attribution_string: str = ""
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class PlannedImageSlot:
    """Validated internal visual placement request from the answer model.

    Args:
        slot_id: Stable slot identifier used to anchor the resolved block.
        query: Provider-search query. This is model output and must not be
            written to logs.
        caption_hint: Optional pedagogical intent for the visual.
        anchor_after_paragraph: Zero-based paragraph index after which the
            image should be inserted.
    """

    slot_id: str
    query: str
    caption_hint: str = ""
    anchor_after_paragraph: int = 0
