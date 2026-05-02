"""
OmniDiag AI — Log Normalizer Module

Parses and normalizes raw probe output into a structured format
suitable for LLM context injection and RAG enrichment.
"""

import re
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# Common Windows Event ID patterns and their meanings
EVENT_ID_MAP = {
    "41":    ("Kernel-Power", "Unexpected shutdown / system restart"),
    "6008":  ("EventLog", "Previous shutdown was unexpected"),
    "219":   ("DriverFrameworks-UserMode", "Driver load warning"),
    "1001":  ("BugCheck", "Blue Screen of Death recorded"),
    "7023":  ("Service Control Manager", "Service terminated with error"),
    "7034":  ("Service Control Manager", "Service crashed unexpectedly"),
    "1000":  ("Application Error", "Application crash recorded"),
    "1001":  ("Windows Error Reporting", "Fault bucket / crash report"),
    "129":   ("Disk", "Disk reset triggered — potential storage issue"),
    "11":    ("Disk", "Driver detected controller error on disk"),
}


@dataclass
class NormalizedEvent:
    """A single normalized Windows event record."""
    event_id: str
    source: str
    level: str
    timestamp: Optional[str]
    message: str
    category: Optional[str] = None
    raw_line: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "level": self.level,
            "timestamp": self.timestamp,
            "category": self.category,
            "message": self.message,
        }


@dataclass
class NormalizerResult:
    """Output of the normalization pipeline."""
    events: list[NormalizedEvent] = field(default_factory=list)
    smart_data: dict = field(default_factory=dict)
    driver_warnings: list[str] = field(default_factory=list)
    service_failures: list[str] = field(default_factory=list)
    bsod_records: list[dict] = field(default_factory=list)
    raw_sections: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    def to_context_string(self, max_chars: int = 80000) -> str:
        """
        Serialize normalized data into an LLM-ready context string.
        Respects a character budget to avoid exceeding context window limits.
        """
        sections = []

        if self.bsod_records:
            sections.append("### BSOD / BugCheck Records\n" +
                          json.dumps(self.bsod_records, indent=2))

        if self.smart_data:
            sections.append("### Storage SMART Data\n" +
                          json.dumps(self.smart_data, indent=2))

        if self.driver_warnings:
            sections.append("### Driver Warnings\n" +
                          "\n".join(f"- {w}" for w in self.driver_warnings))

        if self.service_failures:
            sections.append("### Service Failures\n" +
                          "\n".join(f"- {s}" for s in self.service_failures))

        if self.events:
            event_lines = [json.dumps(e.to_dict()) for e in self.events[:100]]
            sections.append("### Event Log Records (up to 100)\n" +
                          "\n".join(event_lines))

        result = "\n\n".join(sections)
        return result[:max_chars] if len(result) > max_chars else result


class LogNormalizer:
    """
    Transforms raw PowerShell probe output into a structured,
    token-efficient format for LLM analysis.

    The normalizer handles:
    - Windows Event Log entries (XML and text format)
    - SMART disk health data
    - Driver and service status information
    - BSOD / BugCheck records
    """

    # Regex patterns for extracting key data
    _EVENT_PATTERN = re.compile(
        r"(?:EventID|Id)\s*[:=]\s*(\d+).*?(?:Source|ProviderName)\s*[:=]\s*([^\n]+)",
        re.IGNORECASE | re.DOTALL
    )
    _TIMESTAMP_PATTERN = re.compile(
        r"TimeCreated\s*[:=]\s*([^\n]+)|"
        r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})",
        re.IGNORECASE
    )
    _BSOD_PATTERN = re.compile(
        r"BugCheck(?:Code)?\s*[:=]\s*(0x[0-9A-Fa-f]+)",
        re.IGNORECASE
    )
    _SMART_ATTRIBUTE_PATTERN = re.compile(
        r"(\d{1,3})\s+([\w_]+)\s+\d+\s+\d+\s+\d+\s+\S+\s+(\d+)",
        re.IGNORECASE
    )

    def normalize(self, raw_output: str, probe_name: str = "unknown") -> NormalizerResult:
        """
        Main entry point. Parse raw probe string into NormalizerResult.

        Args:
            raw_output: Raw stdout from a probe PowerShell script
            probe_name: Name of the originating probe

        Returns:
            NormalizerResult with all extracted structured data
        """
        result = NormalizerResult()
        result.raw_sections["probe"] = probe_name

        if not raw_output or not raw_output.strip():
            result.stats["status"] = "empty_output"
            return result

        # Split output into logical sections
        lines = raw_output.splitlines()

        result.bsod_records = self._extract_bsod(raw_output)
        result.driver_warnings = self._extract_driver_warnings(lines)
        result.service_failures = self._extract_service_failures(lines)
        result.smart_data = self._extract_smart_data(raw_output)
        result.events = self._extract_events(raw_output)

        result.stats = {
            "total_lines": len(lines),
            "total_chars": len(raw_output),
            "events_found": len(result.events),
            "bsod_records": len(result.bsod_records),
            "driver_warnings": len(result.driver_warnings),
            "service_failures": len(result.service_failures),
        }

        return result

    def _extract_bsod(self, text: str) -> list[dict]:
        records = []
        for match in self._BSOD_PATTERN.finditer(text):
            code = match.group(1).upper()
            records.append({"bugcheck_code": code, "raw_context": text[max(0, match.start()-50):match.end()+100]})
        return records

    def _extract_driver_warnings(self, lines: list[str]) -> list[str]:
        warnings = []
        for line in lines:
            if any(kw in line.lower() for kw in ["driver", "vmci", "warning", "error 219"]):
                stripped = line.strip()
                if stripped and len(stripped) > 10:
                    warnings.append(stripped)
        return warnings[:20]

    def _extract_service_failures(self, lines: list[str]) -> list[str]:
        failures = []
        for line in lines:
            if any(kw in line.lower() for kw in ["failed", "stopped", "error", "service control"]):
                stripped = line.strip()
                if stripped and len(stripped) > 10:
                    failures.append(stripped)
        return failures[:20]

    def _extract_smart_data(self, text: str) -> dict:
        smart = {}
        for match in self._SMART_ATTRIBUTE_PATTERN.finditer(text):
            attr_id, attr_name, raw_value = match.groups()
            smart[attr_id] = {"name": attr_name, "raw_value": raw_value}
        return smart

    def _extract_events(self, text: str) -> list[NormalizedEvent]:
        events = []
        for match in self._EVENT_PATTERN.finditer(text):
            event_id = match.group(1)
            source = match.group(2).strip()
            known = EVENT_ID_MAP.get(event_id)
            events.append(NormalizedEvent(
                event_id=event_id,
                source=source,
                level="Warning" if known else "Information",
                timestamp=None,
                message=known[1] if known else f"Event {event_id} from {source}",
                category=known[0] if known else None,
            ))
        return events[:200]
