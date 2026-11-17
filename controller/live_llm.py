"""
SchedAI Live LLM Interface
Supports live LLM APIs (Google Gemini API / OpenAI API) with graceful
automatic fallback to deterministic MockLLMEngine when API keys or network are unavailable.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from controller.mock_llm import MockLLMEngine

SYSTEM_PROMPT = """
You are SchedAI, an OS CPU scheduling controller for xv6.
Given a natural-language request from a system administrator and process information,
determine the optimal scheduling weight (bounded between 1 and 5, default 1).
Return ONLY a valid JSON object with the following schema:
{
  "pid": <integer>,
  "weight": <integer between 1 and 5>,
  "reason": "<short concise justification in under 6 words>"
}
Do not include markdown fences or any other text.
"""


class LiveLLMEngine:
    def __init__(self):
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.mock_fallback = MockLLMEngine()

    def infer(self, natural_language_prompt: str) -> Dict[str, Any]:
        """
        Attempts to call live LLM API if configured.
        Falls back to MockLLMEngine if no key is set or on network failure.
        """
        if self.gemini_key:
            try:
                res = self._call_gemini(natural_language_prompt)
                if res and "pid" in res and "weight" in res:
                    return res
            except Exception as e:
                pass  # Fall back on any API or parsing error

        if self.openai_key:
            try:
                res = self._call_openai(natural_language_prompt)
                if res and "pid" in res and "weight" in res:
                    return res
            except Exception as e:
                pass  # Fall back on any API or parsing error

        # Fallback to local mock engine
        fallback_res = self.mock_fallback.infer(natural_language_prompt)
        if "error" not in fallback_res:
            fallback_res["reason"] = fallback_res.get("reason", "") + " [offline fallback]"
        return fallback_res

    def _call_gemini(self, prompt: str) -> Optional[Dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{SYSTEM_PROMPT}\nUser Request: {prompt}"
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            candidate = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(candidate)

    def _call_openai(self, prompt: str) -> Optional[Dict[str, Any]]:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            candidate = data["choices"][0]["message"]["content"]
            return json.loads(candidate)
