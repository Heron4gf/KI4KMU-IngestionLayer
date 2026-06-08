"""RobustJudgeModel — GPTModel subclass that repairs malformed JSON
before deepeval's trim_and_load_json gets a chance to crash on it.

Strategy: override generate() and a_generate() to mirror the parent's
logic exactly, but replace the trim_and_load_json() call with our own
json_repair-backed parser.  We call self.load_model() and self.name just
like the parent does — no private attributes, no guessing.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, Tuple, Union

from pydantic import BaseModel
from deepeval.models import GPTModel
from deepeval.utils import check_if_multimodal, convert_to_multi_modal_array
from json_repair import repair_json

logger = logging.getLogger("robust_judge")


def _repair_and_parse(text: str) -> Any:
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


class RobustJudgeModel(GPTModel):
    """Drop-in replacement for GPTModel that tolerates malformed JSON output
    from small models like Gemma by running json_repair before schema parsing.
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

        completion = client.chat.completions.create(
            model=self.name,
            messages=messages,
            temperature=self.temperature,
            **self.generation_kwargs,
        )
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

        completion = await client.chat.completions.create(
            model=self.name,
            messages=messages,
            temperature=self.temperature,
            **self.generation_kwargs,
        )
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
