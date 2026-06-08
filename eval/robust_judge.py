"""RobustJudgeModel — GPTModel subclass that repairs malformed JSON
before deepeval's trim_and_load_json gets a chance to crash on it.

deepeval's a_generate(prompt, schema=...) path does:
    output = await self._call_openai(prompt)   # raw string
    json_output = trim_and_load_json(output)   # crashes on bad escapes
    return schema(**json_output)

We override a_generate to intercept the raw string, run json_repair on it,
then hand the cleaned string back to the parent which calls trim_and_load_json
on already-valid JSON — so it always succeeds.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from deepeval.models import GPTModel
from json_repair import repair_json

logger = logging.getLogger("robust_judge")


class RobustJudgeModel(GPTModel):
    """Drop-in replacement for GPTModel that tolerates malformed JSON output."""

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs) -> Any:
        # Call the grandparent's HTTP layer directly to get the raw string,
        # then repair it before the parent's JSON parsing runs.
        raw: str = await self._a_generate_text(prompt, **kwargs)
        cleaned = self._repair(raw)

        if schema is not None:
            try:
                data = json.loads(cleaned)
                return schema(**data), 0  # (result, cost) — GPTModel convention
            except Exception as exc:
                logger.error(
                    "RobustJudgeModel: JSON repair succeeded but schema parsing failed: %s\nCleaned: %s",
                    exc, cleaned,
                )
                raise

        return cleaned, 0

    # ------------------------------------------------------------------
    # Sync path (used by some deepeval internals)
    # ------------------------------------------------------------------
    def generate(self, prompt: str, schema: Any = None, **kwargs) -> Any:
        raw: str = self._generate_text(prompt, **kwargs)
        cleaned = self._repair(raw)

        if schema is not None:
            data = json.loads(cleaned)
            return schema(**data), 0

        return cleaned, 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _repair(text: str) -> str:
        """Strip markdown fences then run json_repair."""
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
        return repaired

    async def _a_generate_text(self, prompt: str, **kwargs) -> str:
        """Call OpenAI and return the raw string content."""
        response = await self.async_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def _generate_text(self, prompt: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
            **kwargs,
        )
        return response.choices[0].message.content or ""
