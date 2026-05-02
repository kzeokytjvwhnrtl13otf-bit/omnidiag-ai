"""
OmniDiag AI — AI Reasoning Agent Module

Orchestrates the full diagnostic pipeline: context assembly,
LLM API communication, response parsing, and output formatting.
"""

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    _HAS_HTTPX = False


@dataclass
class AgentConfig:
    """Configuration for the AI reasoning agent."""
    api_base: str
    api_key: str
    model: str = "deepseek-v4-flash"
    max_tokens: int = 8192
    temperature: float = 0.1
    timeout_seconds: int = 180


@dataclass
class DiagnosticRequest:
    """A fully assembled request ready for LLM reasoning."""
    system_prompt: str
    user_prompt: str
    probe_name: str
    input_char_count: int
    auto_fix: bool = False


@dataclass
class DiagnosticResponse:
    """Parsed and validated response from the LLM."""
    success: bool
    diagnosis: dict
    raw_response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    error: Optional[str] = None


class OmniDiagAgent:
    """
    The AI reasoning agent at the core of OmniDiag AI.

    Responsible for:
    1. Assembling the final prompt from normalized probe data + RAG context
    2. Calling the LLM API (OpenAI-compatible) with retry logic
    3. Parsing and validating the structured JSON response
    4. Extracting and saving auto-remediation scripts
    """

    SYSTEM_PROMPT = """You are OmniDiag AI, an expert AIOps diagnostic agent specialized in Windows system stability analysis.

Your role is to analyze raw system telemetry data (Event Viewer logs, WHEA errors, BSOD dumps, SMART data, driver conflicts, service failures) and provide:

1. **Root Cause Analysis**: Identify the most likely root cause with confidence levels.
2. **Causal Chain**: Trace the chain of events leading to the failure.
3. **Risk Assessment**: Rate overall system health (Critical / Warning / Healthy).
4. **Remediation Steps**: Actionable fix steps ordered by priority and safety.
5. **Auto-Fix Script**: If requested, a safe PowerShell remediation script with rollback.

Always respond in valid JSON matching this schema:
{
  "summary": "string",
  "health_rating": "Critical | Warning | Healthy",
  "confidence": 0.0-1.0,
  "root_causes": [{"cause": "string", "evidence": ["string"], "confidence": 0.0-1.0, "severity": "critical|high|medium|low"}],
  "causal_chain": "string",
  "risk_factors": ["string"],
  "remediation": [{"step": 1, "action": "string", "command": "string", "risk": "low|medium|high", "rollback": "string"}],
  "auto_fix_script": "string or null"
}

Rules:
- Always cite specific Event IDs, timestamps, and error codes from the provided data.
- Never fabricate data. If insufficient, state what additional probes are needed.
- For auto-fix scripts, always include safety checks and rollback mechanisms.
"""

    def __init__(self, config: AgentConfig):
        self.config = config

    def reason(self, probe_output: str, rag_context: str = "",
               probe_name: str = "unknown", auto_fix: bool = False) -> DiagnosticResponse:
        """
        Execute the full AI reasoning pipeline for a given diagnostic session.

        Args:
            probe_output: Normalized telemetry data from probe collector
            rag_context: Enriched context from RAG pipeline
            probe_name: Name of the originating probe module
            auto_fix: Whether to request remediation script generation

        Returns:
            DiagnosticResponse with parsed diagnosis and token usage stats
        """
        if not self.config.api_key:
            return DiagnosticResponse(
                success=False,
                diagnosis={},
                error="API key not configured. Set LLM_API_KEY in .env file.",
            )

        # Assemble prompt
        user_prompt = self._build_user_prompt(probe_output, rag_context, auto_fix)
        request = DiagnosticRequest(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            probe_name=probe_name,
            input_char_count=len(user_prompt),
            auto_fix=auto_fix,
        )

        # Call LLM with retry
        return self._call_with_retry(request, max_retries=3)

    def _build_user_prompt(self, probe_output: str, rag_context: str,
                           auto_fix: bool) -> str:
        """Assemble the final user prompt from all context sources."""
        parts = ["## System Diagnostic Data\n"]
        parts.append("### Raw Probe Telemetry\n```\n" + probe_output[:60000] + "\n```")

        if rag_context:
            parts.append("\n" + rag_context[:15000])

        parts.append("\n### Analysis Instructions")
        parts.append("- Perform deep root-cause analysis on all data above.")
        parts.append("- Identify anomalies, correlations, and causal chains.")
        parts.append("- Rate overall system health with specific justification.")
        parts.append("- Provide ordered remediation steps by priority and safety.")
        if auto_fix:
            parts.append("- Generate a complete PowerShell auto-fix script with safety checks and rollback.")
        else:
            parts.append("- Do NOT generate auto-fix scripts for this run.")

        return "\n".join(parts)

    def _call_with_retry(self, request: DiagnosticRequest,
                          max_retries: int = 3) -> DiagnosticResponse:
        """Call the LLM API with exponential backoff retry logic."""
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.api_base}/chat/completions"

        for attempt in range(max_retries):
            start = time.monotonic()
            try:
                raw = self._http_post(url, payload, headers)
                latency_ms = int((time.monotonic() - start) * 1000)
                return self._parse_response(raw, latency_ms)
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    return DiagnosticResponse(
                        success=False,
                        diagnosis={},
                        error=f"API call failed after {max_retries} attempts: {str(e)}",
                    )

    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        """Execute HTTP POST using httpx or urllib fallback."""
        if _HAS_HTTPX:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        else:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))

    def _parse_response(self, raw: dict, latency_ms: int) -> DiagnosticResponse:
        """Parse and validate the raw API response."""
        try:
            content = raw["choices"][0]["message"]["content"]
            diagnosis = json.loads(content)
            usage = raw.get("usage", {})
            return DiagnosticResponse(
                success=True,
                diagnosis=diagnosis,
                raw_response=content,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=latency_ms,
            )
        except (KeyError, json.JSONDecodeError) as e:
            return DiagnosticResponse(
                success=False,
                diagnosis={"raw_response": raw},
                error=f"Response parsing failed: {str(e)}",
                latency_ms=latency_ms,
            )
