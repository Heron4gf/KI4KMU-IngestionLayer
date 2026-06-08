"""RobustJudgeModel — GPTModel subclass that:
  1. Repairs malformed JSON (markdown fences, bad escapes) via json_repair
     before deepeval's schema parser sees it.
  2. Retries on 504 / timeout errors with exponential backoff so a slow
     upstream doesn't crash the entire evaluation run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Optional, Tuple, Union

from pydantic import BaseModel
from openai import InternalServerError, APITimeoutError, APIConnectionError
from deepeval.models import GPTModel
from deepeval.utils import check_if_multimodal, convert_to_multi_modal_array
from json_repair import repair_json

logger = logging.getLogger("robust_judge")

_RETRY_EXCEPTIONS = (InternalServerError, APITimeoutError, APIConnectionError)
_MAX_RETRIES = 4
_BASE_DELAY = 5.0   # seconds
_MAX_DELAY  = 60.0  # seconds


def _repair_and_parse(text: str) -> object:
    """Strip markdown fences, run json_repair, return parsed object."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        end = -1 if lines[-1].strip() == "```" else len(lines)
        s = "\n".join(lines[1:end])
    repaired = repair_json(s)
    if repaired != s:
        logger.info("RobustJudgeModel: json_repair mutated output")
        logger.debug("Before: %s", s)
        logger.debug("After:  %s", repaired)
    return json.loads(repaired)


def _backoff(attempt: int) -> float:
    """Full-jitter exponential backoff."""
    ceiling = min(_MAX_DELAY, _BASE_DELAY * 2 ** attempt)
    return random.uniform(0, ceiling)


class RobustJudgeModel(GPTModel):
    """Drop-in replacement for GPTModel that tolerates:
    - Malformed JSON from small models (Gemma, etc.)
    - Transient 504 / timeout errors from a slow upstream
    """

    def generate(
        self, prompt: str, schema: Optional[BaseModel] = None
    ) -> Tuple[Union[str, BaseModel], float]:
        client = self.load_model(async_mode=False)

        if check_if_multimodal(prompt):
            content = self.generate_content(convert_to_multi_modal_array(input=prompt))
        else:
            content = [{"type": "text", "text": prompt}]
        messages = [{"role": "user", "content": content}]

        last_exc: Exception = RuntimeError("no attempts")
        for attempt in range(_MAX_RETRIES):
            try:
                completion = client.chat.completions.create(
                    model=self.name,
                    messages=messages,
                    temperature=self.temperature,
                    **self.generation_kwargs,
                )
                break
            except _RETRY_EXCEPTIONS as exc:
                last_exc = exc
                delay = _backoff(attempt)
                logger.warning(
                    "RobustJudgeModel [sync] attempt %d/%d failed (%s) — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, exc, delay,
                )
                import time; time.sleep(delay)
        else:
            raise last_exc

        output = completion.choices[0].message.content or ""
        cost = self.calculate_cost(
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
        )
        self._update_llm_span_from_completion(completion, messages)

        if schema:
            data = _repair_and_parse(output)
            return schema.model_validate(data), cost
        return output, cost

    async def a_generate(
        self, prompt: str, schema: Optional[BaseModel] = None
    ) -> Tuple[Union[str, BaseModel], float]:
        client = self.load_model(async_mode=True)

        if check_if_multimodal(prompt):
            content = self.generate_content(convert_to_multi_modal_array(input=prompt))
        else:
            content = [{"type": "text", "text": prompt}]
        messages = [{"role": "user", "content": content}]

        last_exc: Exception = RuntimeError("no attempts")
        for attempt in range(_MAX_RETRIES):
            try:
                completion = await client.chat.completions.create(
                    model=self.name,
                    messages=messages,
                    temperature=self.temperature,
                    **self.generation_kwargs,
                )
                break
            except _RETRY_EXCEPTIONS as exc:
                last_exc = exc
                delay = _backoff(attempt)
                logger.warning(
                    "RobustJudgeModel [async] attempt %d/%d failed (%s) — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, exc, delay,
                )
                await asyncio.sleep(delay)
        else:
            raise last_exc

        output = completion.choices[0].message.content or ""
        cost = self.calculate_cost(
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
        )
        self._update_llm_span_from_completion(completion, messages)

        if schema:
            data = _repair_and_parse(output)
            return schema.model_validate(data), cost
        return output, cost
