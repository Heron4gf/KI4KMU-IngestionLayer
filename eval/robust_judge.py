"""RobustJudgeModel — GPTModel subclass that:
  1. Repairs malformed JSON (markdown fences, bad escapes) via json_repair.
  2. Fills in missing required fields with safe defaults so Pydantic
     validation never crashes on incomplete model output.
  3. Retries on 504 / timeout errors with exponential backoff.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Optional, Tuple, Union

from pydantic import BaseModel, ValidationError
from openai import InternalServerError, APITimeoutError, APIConnectionError
from deepeval.models import GPTModel
from deepeval.utils import check_if_multimodal, convert_to_multi_modal_array
from json_repair import repair_json

logger = logging.getLogger("robust_judge")

_RETRY_EXCEPTIONS = (InternalServerError, APITimeoutError, APIConnectionError)
_MAX_RETRIES = 4
_BASE_DELAY = 5.0
_MAX_DELAY = 60.0

# Safe defaults injected when the model omits a required field.
# Covers every schema deepeval uses for its built-in metrics.
_FIELD_DEFAULTS: dict = {
    "verdict": "no",
    "verdicts": [],
    "reason": "(no reason provided)",
    "score": 0,
    "statements": [],
    "truths": [],
    "claims": [],
}


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


def _fill_defaults(data: object, schema: type[BaseModel]) -> object:
    """Recursively walk parsed data and inject _FIELD_DEFAULTS for any field
    that the schema requires but the model omitted."""
    if not isinstance(data, dict):
        return data

    # Fill top-level missing fields
    for field_name, field_info in schema.model_fields.items():
        if field_name not in data and field_name in _FIELD_DEFAULTS:
            logger.warning(
                "RobustJudgeModel: model omitted required field '%s', injecting default",
                field_name,
            )
            data[field_name] = _FIELD_DEFAULTS[field_name]

    # Recurse into list items if the list items are themselves BaseModel schemas
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        # Unwrap Optional / list generics to find nested BaseModel types
        nested = _unwrap_list_annotation(annotation)
        if nested is not None and isinstance(data.get(field_name), list):
            data[field_name] = [
                _fill_defaults(item, nested) if isinstance(item, dict) else item
                for item in data[field_name]
            ]

    return data


def _unwrap_list_annotation(annotation) -> type[BaseModel] | None:
    """Return the item type if annotation is list[SomeBaseModel], else None."""
    try:
        import typing
        origin = getattr(annotation, "__origin__", None)
        if origin is list:
            args = getattr(annotation, "__args__", ())
            if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                return args[0]
        # Handle Optional[list[X]]
        if origin is Union:
            for arg in getattr(annotation, "__args__", ()):
                result = _unwrap_list_annotation(arg)
                if result is not None:
                    return result
    except Exception:
        pass
    return None


try:
    from typing import Union  # noqa: ensure Union is always available above
except ImportError:
    pass


def _backoff(attempt: int) -> float:
    ceiling = min(_MAX_DELAY, _BASE_DELAY * 2 ** attempt)
    return random.uniform(0, ceiling)


def _validate(data: object, schema: type[BaseModel]) -> BaseModel:
    """Validate data against schema, filling defaults on ValidationError."""
    try:
        return schema.model_validate(data)
    except ValidationError:
        filled = _fill_defaults(data if isinstance(data, dict) else {}, schema)
        try:
            return schema.model_validate(filled)
        except ValidationError as exc:
            logger.error(
                "RobustJudgeModel: schema validation failed even after filling defaults.\n"
                "Schema: %s\nData: %s\nErrors: %s",
                schema.__name__, filled, exc,
            )
            raise


class RobustJudgeModel(GPTModel):
    """Drop-in replacement for GPTModel that tolerates malformed or
    incomplete JSON output from small models like Gemma.
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
            return _validate(data, schema), cost
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
            return _validate(data, schema), cost
        return output, cost
