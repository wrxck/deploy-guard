#!/usr/bin/env python3
"""
Claude Code PostToolUse hook (advisory).
After a deploy command completes, runs HTTP smoke tests against
configured endpoints. Config file: ~/.claude/hooks/deploy_endpoints.json
Expected shape:
  {
    "defaults": {"timeout": 5, "max_response_time": 2.0},
    "<service_name>": {"url": "https://host/health", "timeout": 5}
  }
URLs must be http or https; other schemes (file://, etc.) are rejected.
If the deployed service is not configured, this hook exits silently.
"""

import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse


ENDPOINTS_FILE = os.path.expanduser('~/.claude/hooks/deploy_endpoints.json')

DEPLOY_PATTERNS = [
    r'\bsystemctl\s+(?:start|restart|reload|enable\s+--now)\b',
    r'\b(?:docker|podman)\s+compose\s+up\b',
    r'\b(?:docker|podman)\s+(?:restart|start|run)\b',
    r'\b(?:docker|podman)\s+stack\s+deploy\b',
    r'\bdocker-compose\s+up\b',
    r'\bkubectl\s+(?:apply|rollout\s+restart|set\s+image)\b',
    r'\b(?:cp|install|mv)\s+[^\n;&|]*\s+/usr/local/bin/(?:\S+)?',
    r'\bfleet\s+deploy\b',
    r'\bservice\s+\S+\s+(?:restart|start|reload)\b',
]

DEPLOY_RE = re.compile('|'.join(DEPLOY_PATTERNS))


def is_deploy_command(command: str) -> bool:
    return bool(DEPLOY_RE.search(command))


def load_endpoints() -> dict:
    try:
        with open(ENDPOINTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def extract_service_name(command: str):
    m = re.search(r'\bsystemctl\s+(?:start|restart|reload|enable\s+--now)\s+(\S+)', command)
    if m:
        name = m.group(1)
        if name.endswith('.service'):
            name = name[:-len('.service')]
        return name
    m = re.search(r'\b(?:docker|podman)\s+(?:restart|start)\s+(\S+)', command)
    if m:
        return m.group(1)
    m = re.search(r'\bservice\s+(\S+)\s+(?:restart|start|reload)', command)
    if m:
        return m.group(1)
    m = re.search(r'\b(?:cp|install|mv)\s+\S+\s+/usr/local/bin/(\S+)', command)
    if m:
        return m.group(1)
    m = re.search(r'\bfleet\s+deploy\s+(\S+)', command)
    if m:
        return m.group(1)
    return None


def safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def run_smoke_test(url: str, timeout: int = 5) -> dict:
    try:
        result = subprocess.run(
            [
                'curl', '-sS', '-o', '/dev/null',
                '-w', '%{http_code}|%{time_total}',
                '--max-time', str(timeout),
                '--proto', '=http,https',
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        parts = result.stdout.strip().split('|')
        if len(parts) == 2:
            return {
                'url': url,
                'status': int(parts[0]),
                'time': float(parts[1]),
                'error': None,
            }
        return {
            'url': url,
            'status': 0,
            'time': 0,
            'error': result.stderr.strip() or 'unexpected curl output',
        }
    except (subprocess.TimeoutExpired, Exception) as e:
        return {
            'url': url,
            'status': 0,
            'time': 0,
            'error': str(e),
        }


def emit_context(context: str):
    output = {
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': context,
        }
    }
    print(json.dumps(output))


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = input_data.get('tool_input', {}) or {}
    command = tool_input.get('command', '') or ''

    if not command or not is_deploy_command(command):
        sys.exit(0)

    config = load_endpoints()
    defaults = config.get('defaults', {}) if isinstance(config, dict) else {}
    max_time = defaults.get('max_response_time', 2.0)
    default_timeout = defaults.get('timeout', 5)

    service_name = extract_service_name(command)
    endpoints_to_test = []

    if service_name and isinstance(config.get(service_name), dict):
        endpoints_to_test.append(config[service_name])
    elif service_name:
        emit_context(
            f'no smoke endpoint configured for {service_name}; skipping smoke test. '
            f'add it to {ENDPOINTS_FILE} to enable.'
        )
        sys.exit(0)
    else:
        for key, ep in config.items():
            if key != 'defaults' and isinstance(ep, dict) and 'url' in ep:
                endpoints_to_test.append(ep)

    if not endpoints_to_test:
        sys.exit(0)

    results = []
    all_passed = True
    for ep in endpoints_to_test:
        url = ep.get('url', '')
        timeout = ep.get('timeout', default_timeout)
        if not url or not safe_url(url):
            results.append({
                'url': url or '<missing>',
                'status': 0,
                'time': 0,
                'error': 'url rejected: must be http or https',
                'passed': False,
            })
            all_passed = False
            continue
        result = run_smoke_test(url, timeout)
        passed = (
            result['error'] is None
            and 200 <= result['status'] < 400
            and result['time'] <= max_time
        )
        result['passed'] = passed
        if not passed:
            all_passed = False
        results.append(result)

    if not results:
        sys.exit(0)

    lines = [f'deploy smoke test results for: {command[:80]}']
    for r in results:
        if r.get('error'):
            lines.append(f"  FAIL {r['url']}: {r['error']}")
        elif not r['passed']:
            reasons = []
            if r['status'] < 200 or r['status'] >= 400:
                reasons.append(f"HTTP {r['status']}")
            if r['time'] > max_time:
                reasons.append(f"{r['time']:.2f}s > {max_time}s threshold")
            lines.append(f"  FAIL {r['url']}: {', '.join(reasons)}")
        else:
            lines.append(f"  PASS {r['url']}: HTTP {r['status']} in {r['time']:.2f}s")

    if not all_passed:
        lines.append('')
        lines.append('WARNING: one or more smoke tests failed — investigate before proceeding')

    emit_context('\n'.join(lines))
    sys.exit(0)


if __name__ == '__main__':
    main()
