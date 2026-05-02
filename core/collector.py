"""
OmniDiag AI — Probe Collector Module

Responsible for executing PowerShell diagnostic probes and collecting
structured telemetry output for downstream processing.
"""

import subprocess
import time
import json
from pathlib import Path
from typing import Optional


PROBE_TIMEOUT_SECONDS = 120


class ProbeResult:
    """Structured container for probe execution results."""

    def __init__(self, probe_name: str, raw_output: str, duration_ms: int,
                 exit_code: int, stderr: str = ""):
        self.probe_name = probe_name
        self.raw_output = raw_output
        self.duration_ms = duration_ms
        self.exit_code = exit_code
        self.stderr = stderr
        self.success = exit_code == 0
        self.char_count = len(raw_output)

    def to_dict(self) -> dict:
        return {
            "probe_name": self.probe_name,
            "success": self.success,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "char_count": self.char_count,
            "raw_output": self.raw_output,
            "stderr": self.stderr,
        }


class ProbeCollector:
    """
    Executes PowerShell diagnostic probes and aggregates their output.

    Each probe is a self-contained PowerShell script that collects
    specific telemetry data from the target Windows system.
    """

    def __init__(self, probes_dir: Path, verbose: bool = False):
        self.probes_dir = probes_dir
        self.verbose = verbose
        self._results: list[ProbeResult] = []

    def run(self, probe_name: str, probe_file: str) -> ProbeResult:
        """
        Execute a single PowerShell probe script.

        Args:
            probe_name: Logical name of the probe (e.g., 'health_check')
            probe_file: Filename of the PowerShell script

        Returns:
            ProbeResult containing raw output and execution metadata
        """
        probe_path = self.probes_dir / probe_file

        if not probe_path.exists():
            return ProbeResult(
                probe_name=probe_name,
                raw_output=f"[ERROR] Probe script not found: {probe_path}",
                duration_ms=0,
                exit_code=-1,
            )

        start_time = time.monotonic()

        try:
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(probe_path)],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_SECONDS,
                encoding="utf-8",
                errors="replace",
            )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            output = result.stdout or ""

            probe_result = ProbeResult(
                probe_name=probe_name,
                raw_output=output,
                duration_ms=duration_ms,
                exit_code=result.returncode,
                stderr=result.stderr or "",
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            probe_result = ProbeResult(
                probe_name=probe_name,
                raw_output=f"[TIMEOUT] Probe exceeded {PROBE_TIMEOUT_SECONDS}s limit.",
                duration_ms=duration_ms,
                exit_code=-2,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            probe_result = ProbeResult(
                probe_name=probe_name,
                raw_output=f"[EXCEPTION] {type(e).__name__}: {str(e)}",
                duration_ms=duration_ms,
                exit_code=-3,
            )

        self._results.append(probe_result)
        return probe_result

    def run_all(self, probes: dict) -> list[ProbeResult]:
        """Execute multiple probes sequentially and collect results."""
        results = []
        for probe_name, probe_info in probes.items():
            result = self.run(probe_name, probe_info["file"])
            results.append(result)
        return results

    def aggregate(self) -> str:
        """
        Aggregate all collected probe outputs into a single string
        suitable for injection into an LLM context window.
        """
        parts = []
        for result in self._results:
            header = f"\n{'='*60}\n## PROBE: {result.probe_name.upper()}\n"
            header += f"## Status: {'OK' if result.success else 'FAILED'} | "
            header += f"Duration: {result.duration_ms}ms | "
            header += f"Output size: {result.char_count:,} chars\n{'='*60}\n"
            parts.append(header + result.raw_output)

        return "\n".join(parts)

    def get_summary(self) -> dict:
        """Return a summary of all probe executions."""
        return {
            "total_probes": len(self._results),
            "successful": sum(1 for r in self._results if r.success),
            "failed": sum(1 for r in self._results if not r.success),
            "total_chars": sum(r.char_count for r in self._results),
            "total_duration_ms": sum(r.duration_ms for r in self._results),
        }
