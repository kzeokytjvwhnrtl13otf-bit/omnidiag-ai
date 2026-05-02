#!/usr/bin/env python3
"""
OmniDiag — System Stability Analysis & Automated Remediation Engine

This is the main CLI entry point that orchestrates:
  1. Probe execution (PowerShell diagnostic scripts)
  2. Log normalization and structuring
  3. LLM-based root-cause analysis (OpenAI-compatible API)
  4. Auto-remediation script generation
"""

import io
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    import urllib.request
    import urllib.error
    httpx = None

# Core engine modules
from core.collector import ProbeCollector
from core.normalizer import LogNormalizer
from core.rag import RAGPipeline

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.resolve()
PROBES_DIR = BASE_DIR / "probes"
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
FIXES_DIR = OUTPUT_DIR / "fixes"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

# Ensure output directories exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
FIXES_DIR.mkdir(parents=True, exist_ok=True)

# LLM API Configuration (OpenAI-compatible endpoint)
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))

# Available probe modules
PROBES = {
    "health_check": {
        "file": "health_check.ps1",
        "description": "Quick system health scan (SMART, devices, AV, OS image)",
        "tier": "quick",
    },
    "full_diag": {
        "file": "full_diag.ps1",
        "description": "Full BSOD & crash analysis (Kernel-Power, WHEA, BugCheck, Minidumps)",
        "tier": "full",
    },
    "deep_scan": {
        "file": "deep_scan.ps1",
        "description": "Deep system audit (storage, CBS, services, drivers, crash hotspots)",
        "tier": "deep",
    },
    "quick_check": {
        "file": "quick_check.ps1",
        "description": "Real-time error monitor (last 10 minutes + high-resource process detection)",
        "tier": "quick",
    },
    "get_events": {
        "file": "get_events.ps1",
        "description": "Time-range event extraction for incident forensics",
        "tier": "forensic",
    },
}

# ─── System Prompt for AI Agent ──────────────────────────────────────────────

SYSTEM_PROMPT = """Role: System Diagnostic Analyzer.
Task: Analyze the following raw Windows system telemetry data (Event Viewer logs, WHEA errors, BSOD dumps, SMART data, driver conflicts, service failures) and provide a structured diagnostic report.

You must provide:

1. **Root Cause Analysis**: Identify the most likely root cause of system instability with confidence levels.
2. **Causal Chain**: Trace the chain of events that led to the failure (e.g., driver conflict → kernel panic → BSOD).
3. **Risk Assessment**: Rate the overall system health (Critical / Warning / Healthy) with specific risk factors.
4. **Remediation Steps**: Provide actionable fix steps ordered by priority and impact.
5. **Auto-Fix Script**: If requested, generate a safe PowerShell remediation script with rollback capabilities.

## Output Format
Always respond in the following structured JSON format:
```json
{
  "summary": "One-line summary of the diagnosis",
  "health_rating": "Critical | Warning | Healthy",
  "confidence": 0.0-1.0,
  "root_causes": [
    {
      "cause": "Description of root cause",
      "evidence": ["List of supporting evidence from logs"],
      "confidence": 0.0-1.0,
      "severity": "critical | high | medium | low"
    }
  ],
  "causal_chain": "A → B → C narrative of the failure sequence",
  "risk_factors": ["List of ongoing risk factors"],
  "remediation": [
    {
      "step": 1,
      "action": "What to do",
      "command": "PowerShell command if applicable",
      "risk": "low | medium | high",
      "rollback": "How to undo this step"
    }
  ],
  "auto_fix_script": "Full PowerShell script (only if --auto-fix is enabled)"
}
```

## Rules
- Always cite specific Event IDs, timestamps, and error codes from the provided data.
- Never fabricate data — if information is insufficient, explicitly state what additional probes should be run.
- For auto-fix scripts, always include safety checks and rollback mechanisms.
- Prioritize non-destructive remediation steps over destructive ones.
"""

# ─── Core Functions ──────────────────────────────────────────────────────────

def print_banner():
    """Display the OmniDiag AI banner."""
    banner = r"""
   ____                  _ ____  _                  _    ___
  / __ \                (_)  _ \(_)                / \  |_ _|
 | |  | |_ __ ___  _ __ _| | | |_  __ _  __ _   / _ \  | |
 | |  | | '_ ` _ \| '_ \| | | | |/ _` |/ _` | / ___ \ | |
 | |__| | | | | | | | | | | |_| | | (_| | (_| |/ /   \ \| |
  \____/|_| |_| |_|_| |_|_|____/|_|\__,_|\__, /_/     \_\___|
                                           __/ |
                                          |___/
    """
    print("\033[36m" + banner + "\033[0m")
    print("\033[90m  System Stability Analysis & Remediation Engine\033[0m")
    print("\033[90m  ─────────────────────────────────────────────\033[0m\n")


def run_probe(probe_name: str, verbose: bool = False) -> str:
    """
    Execute a PowerShell probe and capture its output.

    Delegates to core.collector.ProbeCollector for structured execution
    with timeout handling and metadata tracking.

    Args:
        probe_name: Name of the probe module (e.g., 'health_check')
        verbose: Whether to print real-time output

    Returns:
        Captured probe output as a string
    """
    if probe_name not in PROBES:
        print(f"\033[31m[ERROR] Unknown probe: {probe_name}\033[0m")
        print(f"Available probes: {', '.join(PROBES.keys())}")
        sys.exit(1)

    probe_info = PROBES[probe_name]
    collector = ProbeCollector(PROBES_DIR, verbose=verbose)

    print(f"\033[33m[PROBE] Running {probe_name} ({probe_info['description']})...\033[0m")

    result = collector.run(probe_name, probe_info["file"])

    if verbose and result.raw_output:
        print("\033[90m" + result.raw_output + "\033[0m")

    if result.success:
        print(f"\033[32m[PROBE] {probe_name} completed — "
              f"captured {result.char_count} chars in {result.duration_ms}ms\033[0m")
    else:
        print(f"\033[31m[PROBE] {probe_name} failed (exit={result.exit_code})\033[0m")

    return result.raw_output


def load_knowledge_context() -> str:
    """
    Load RAG knowledge base files to enrich the AI context.

    Delegates to core.rag.RAGPipeline for structured knowledge retrieval.

    Returns:
        Concatenated knowledge base content for LLM injection
    """
    pipeline = RAGPipeline(KNOWLEDGE_DIR)
    stats = pipeline.get_stats()

    # Build a simple combined context from all loaded KB files
    context_parts = []
    for kb_file in KNOWLEDGE_DIR.glob("*.json"):
        try:
            with open(kb_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            context_parts.append(
                f"\n--- Knowledge Base: {kb_file.stem} ---\n"
                f"{json.dumps(data, indent=2, ensure_ascii=False)[:5000]}"
            )
        except Exception:
            pass

    return "\n".join(context_parts) if context_parts else ""


def call_llm_api(probe_output: str, knowledge_context: str, auto_fix: bool = False) -> dict:
    """
    Send diagnostic data to LLM for AI-powered analysis.

    Args:
        probe_output: Raw probe telemetry data
        knowledge_context: RAG knowledge base context
        auto_fix: Whether to request auto-remediation script generation

    Returns:
        Parsed JSON response from the AI agent
    """
    if not LLM_API_KEY:
        print("\033[31m[ERROR] LLM_API_KEY not set. Please configure .env file.\033[0m")
        print("  Set your OpenAI-compatible API key in the .env file.")
        sys.exit(1)

    user_prompt = f"""## System Diagnostic Data

The following telemetry data was collected from the target system. Analyze it thoroughly and provide your diagnosis.

### Raw Probe Output
```
{probe_output}
```

{f'''### Knowledge Base Context
{knowledge_context}
''' if knowledge_context else ''}

### Instructions
- Perform deep root-cause analysis on the above data.
- Identify all anomalies, correlations, and causal chains.
- Rate overall system health.
- Provide ordered remediation steps.
{"- Generate an auto-fix PowerShell script with safety checks and rollback." if auto_fix else "- Do NOT generate auto-fix scripts for this run."}
"""

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    print(f"\033[35m[AI] Sending {len(user_prompt):,} chars to LLM ({LLM_MODEL})...\033[0m")
    print(f"\033[90m     Estimated input tokens: ~{len(user_prompt) // 3:,}\033[0m")

    try:
        if httpx:
            with httpx.Client(timeout=180) as client:
                response = client.post(
                    f"{LLM_API_BASE}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
        else:
            # Fallback to urllib
            req = urllib.request.Request(
                f"{LLM_API_BASE}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))

        ai_content = result["choices"][0]["message"]["content"]

        # Parse JSON response
        try:
            diagnosis = json.loads(ai_content)
        except json.JSONDecodeError:
            diagnosis = {"raw_response": ai_content, "parse_error": True}

        token_usage = result.get("usage", {})
        print(f"\033[35m[AI] Analysis complete — "
              f"Input: {token_usage.get('prompt_tokens', 'N/A')} tokens, "
              f"Output: {token_usage.get('completion_tokens', 'N/A')} tokens\033[0m")

        return diagnosis

    except Exception as e:
        print(f"\033[31m[ERROR] LLM API call failed: {e}\033[0m")
        return {"error": str(e)}


def save_report(diagnosis: dict, probe_name: str) -> Path:
    """Save the diagnostic report to a file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"diagnosis_{probe_name}_{timestamp}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(diagnosis, f, indent=2, ensure_ascii=False)

    # Also generate a human-readable markdown report
    md_path = REPORTS_DIR / f"diagnosis_{probe_name}_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# OmniDiag AI — Diagnostic Report\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**Probe**: {probe_name}  \n")
        f.write(f"**Model**: {LLM_MODEL}  \n\n")
        f.write(f"---\n\n")

        if "summary" in diagnosis:
            f.write(f"## Summary\n\n{diagnosis['summary']}\n\n")
            f.write(f"**Health Rating**: `{diagnosis.get('health_rating', 'N/A')}`  \n")
            f.write(f"**Confidence**: `{diagnosis.get('confidence', 'N/A')}`  \n\n")

        if "root_causes" in diagnosis:
            f.write(f"## Root Causes\n\n")
            for i, rc in enumerate(diagnosis["root_causes"], 1):
                f.write(f"### {i}. {rc.get('cause', 'Unknown')}\n")
                f.write(f"- **Severity**: {rc.get('severity', 'N/A')}\n")
                f.write(f"- **Confidence**: {rc.get('confidence', 'N/A')}\n")
                if "evidence" in rc:
                    f.write(f"- **Evidence**:\n")
                    for ev in rc["evidence"]:
                        f.write(f"  - {ev}\n")
                f.write("\n")

        if "causal_chain" in diagnosis:
            f.write(f"## Causal Chain\n\n{diagnosis['causal_chain']}\n\n")

        if "remediation" in diagnosis:
            f.write(f"## Remediation Steps\n\n")
            for step in diagnosis["remediation"]:
                f.write(f"**Step {step.get('step', '?')}**: {step.get('action', '')}\n")
                if "command" in step:
                    f.write(f"```powershell\n{step['command']}\n```\n")
                f.write(f"- Risk: `{step.get('risk', 'N/A')}` | Rollback: {step.get('rollback', 'N/A')}\n\n")

        if "auto_fix_script" in diagnosis and diagnosis["auto_fix_script"]:
            f.write(f"## Auto-Fix Script\n\n```powershell\n{diagnosis['auto_fix_script']}\n```\n")

    print(f"\033[32m[REPORT] JSON saved: {report_path}\033[0m")
    print(f"\033[32m[REPORT] Markdown saved: {md_path}\033[0m")

    return report_path


def save_fix_script(diagnosis: dict, probe_name: str) -> Path | None:
    """Extract and save the auto-fix script if present."""
    script = diagnosis.get("auto_fix_script")
    if not script:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fix_path = FIXES_DIR / f"fix_{probe_name}_{timestamp}.ps1"

    with open(fix_path, "w", encoding="utf-8") as f:
        f.write(f"# Auto-generated by OmniDiag AI — {datetime.now()}\n")
        f.write(f"# Probe: {probe_name} | Model: {LLM_MODEL}\n")
        f.write(f"# ⚠️  REVIEW CAREFULLY BEFORE EXECUTION\n\n")
        f.write(script)

    print(f"\033[33m[FIX] Remediation script saved: {fix_path}\033[0m")
    print(f"\033[33m[FIX] ⚠️  Please review the script before running it!\033[0m")

    return fix_path


# ─── CLI Commands ────────────────────────────────────────────────────────────

def cmd_collect(args):
    """Collect probe data without AI analysis."""
    probe_name = args.probe or "health_check"
    output = run_probe(probe_name, verbose=args.verbose)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"raw_{probe_name}_{timestamp}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\033[32m[DONE] Raw probe output saved: {out_path}\033[0m")


def cmd_diagnose(args):
    """Run probe + AI-powered diagnosis."""
    probe_name = args.probe or "full_diag"

    # Step 1: Collect
    probe_output = run_probe(probe_name, verbose=args.verbose)

    # Step 2: Enrich with RAG
    knowledge = load_knowledge_context()
    if knowledge:
        print(f"\033[90m[RAG] Loaded {len(knowledge):,} chars of knowledge context\033[0m")

    # Step 3: AI Analysis
    diagnosis = call_llm_api(probe_output, knowledge, auto_fix=args.auto_fix)

    # Step 4: Save reports
    save_report(diagnosis, probe_name)

    # Step 5: Save fix script if applicable
    if args.auto_fix:
        save_fix_script(diagnosis, probe_name)

    # Step 6: Print summary
    print("\n" + "=" * 60)
    if "summary" in diagnosis:
        health = diagnosis.get("health_rating", "Unknown")
        color = {"Critical": "31", "Warning": "33", "Healthy": "32"}.get(health, "37")
        print(f"\033[{color}m  Health: {health}\033[0m")
        print(f"  Summary: {diagnosis['summary']}")
    elif "error" in diagnosis:
        print(f"\033[31m  Error: {diagnosis['error']}\033[0m")
    print("=" * 60 + "\n")


def cmd_list(args):
    """List available probe modules."""
    print("\033[36mAvailable Probe Modules:\033[0m\n")
    for name, info in PROBES.items():
        tier_colors = {"quick": "32", "full": "33", "deep": "35", "forensic": "36"}
        color = tier_colors.get(info["tier"], "37")
        status = "✅" if (PROBES_DIR / info["file"]).exists() else "❌"
        print(f"  {status} \033[1m{name:<16}\033[0m  "
              f"\033[{color}m[{info['tier']}]\033[0m  "
              f"{info['description']}")
    print()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="OmniDiag — Enterprise System Stability Analysis Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # collect
    p_collect = subparsers.add_parser("collect", help="Collect probe data without AI analysis")
    p_collect.add_argument("--probe", "-p", choices=PROBES.keys(), default="health_check",
                           help="Probe module to run")
    p_collect.add_argument("--verbose", "-v", action="store_true", help="Show real-time output")

    # diagnose
    p_diag = subparsers.add_parser("diagnose", help="Run probe + AI-powered diagnosis")
    p_diag.add_argument("--probe", "-p", choices=PROBES.keys(), default="full_diag",
                        help="Probe module to run")
    p_diag.add_argument("--verbose", "-v", action="store_true", help="Show real-time output")
    p_diag.add_argument("--auto-fix", action="store_true",
                        help="Generate auto-remediation script")

    # list
    subparsers.add_parser("list", help="List available probe modules")

    args = parser.parse_args()

    if args.command == "collect":
        cmd_collect(args)
    elif args.command == "diagnose":
        cmd_diagnose(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
