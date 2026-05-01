# Contributing to OmniDiag AI

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## 🏗️ Development Setup

1. Clone the repository
2. Install Python 3.10+
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and configure your API key

## 📝 Adding New Probes

Probe modules are PowerShell scripts in the `probes/` directory. To add a new probe:

1. Create a new `.ps1` file in `probes/`
2. Follow the output format convention (structured text with section headers)
3. Register the probe in `omnidiag.py` → `PROBES` dictionary
4. Test the probe: `python omnidiag.py collect --probe your_probe`

### Probe Guidelines

- Use `Write-Host` for display output, `Write-Output` for data output
- Include error handling with `try/catch` blocks
- Set reasonable timeouts for WMI/CIM queries
- Document what the probe collects in the module header

## 🧠 Improving AI Prompts

The system prompt is defined in `omnidiag.py` → `SYSTEM_PROMPT`. When modifying:

- Keep the structured JSON output format
- Add domain-specific instructions for new failure categories
- Test with real probe output before submitting

## 📚 Expanding the Knowledge Base

Add entries to JSON files in `knowledge/`:

- `whea_codes.json` — WHEA error code reference
- `bugcheck_codes.json` — Windows BugCheck code reference
- `known_issues.json` — Historical incident patterns

## 🔀 Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with clear commit messages
3. Test with at least one real diagnostic session
4. Submit a PR with a description of what changed and why

## 📜 Code Style

- Python: Follow PEP 8, use type hints
- PowerShell: Use approved verbs, include comment-based help
- All files: UTF-8 encoding, LF line endings
