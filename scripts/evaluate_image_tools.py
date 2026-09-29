"""Evaluate real model tool selection without executing paid image tools.

This measures the tool contract against authored fixtures, not production memory
routing or image quality. Reports contain case IDs, choices and timings only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'src/main/python')]
from openai import AsyncOpenAI
from config import settings
from services.conversation.image_generation import IMAGE_TOOL, validate_image_payload


async def evaluate(output: Path, model: str) -> int:
    """Run each fixture once; never execute a tool or retain generated content."""
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key:
        output.write_text(json.dumps({'status': 'not_run', 'reason': 'OPENROUTER_API_KEY unavailable'}, indent=2))
        return 2
    fixtures = json.loads((ROOT / 'tests/evaluations/image_tools.json').read_text())
    results = []
    async with AsyncOpenAI(base_url='https://openrouter.ai/api/v1', api_key=key, timeout=30) as client:
        for case in fixtures:
            started = time.monotonic()
            row = {'case_id': case['id']}
            try:
                response = await client.chat.completions.create(model=model, messages=case['messages'], tools=[IMAGE_TOOL], tool_choice='auto', max_tokens=1000)
                calls = response.choices[0].message.tool_calls or []
                selected = [call.function.name for call in calls] or ['chat']
                valid = len(calls) <= 1 and all(name in case['allowed'] for name in selected)
                if calls:
                    payload = validate_image_payload(json.loads(calls[0].function.arguments))
                    valid = valid and (not case.get('presentation') or payload['presentation'] == case['presentation'])
                row.update(selected=selected, passed=valid)
            except Exception as exc:
                row.update(passed=False, error_type=type(exc).__name__)
            row['elapsed_ms'] = round((time.monotonic() - started) * 1000)
            results.append(row)
    output.write_text(json.dumps({'status': 'completed', 'model': model, 'results': results}, ensure_ascii=False, indent=2))
    return 0 if all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/tmp/areqa-image-tool-evaluation.json'))
    parser.add_argument('--model', default=settings.model_main_instruct)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(evaluate(args.output, args.model)))
