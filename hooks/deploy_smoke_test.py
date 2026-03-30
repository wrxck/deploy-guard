#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Bash commands.
After a deploy command completes, runs HTTP smoke tests against
the deployed service to verify it responds within acceptable latency.
"""

import json
import os
import re
import subprocess
import sys


ENDPOINTS_FILE = os.path.expanduser('~/.claude/hooks/deploy_endpoints.json')

# patterns that indicate a deploy just happened
DEPLOY_PATTERNS = [
    r'\bsystemctl\s+(start|restart)\b',
    r'\bdocker\s+compose\s+up\b',
    r'\bdocker\s+restart\b',
    r'\bcp\s+.*\s+/usr/local/bin/',
]


def is_deploy_command(command: str) -> bool:
    """check if the command is a deploy-related action"""
    return any(re.search(p, command) for p in DEPLOY_PATTERNS)


def load_endpoints() -> dict:
    """load endpoint configuration from json file"""
    try:
        with open(ENDPOINTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def extract_service_name(command: str) -> str | None:
    """try to extract a service/container name from the deploy command"""
    # systemctl start/restart <service>
    m = re.search(r'\bsystemctl\s+(?:start|restart)\s+(\S+)', command)
    if m:
        return m.group(1)

    # docker restart <container>
    m = re.search(r'\bdocker\s+restart\s+(\S+)', command)
    if m:
        return m.group(1)

    # cp <binary> /usr/local/bin/<name>
    m = re.search(r'\bcp\s+\S+\s+/usr/local/bin/(\S+)', command)
    if m:
        return m.group(1)

    # docker compose up (use directory name as hint)
    if re.search(r'\bdocker\s+compose\s+up\b', command):
        return None  # could be multiple services

    return None


def run_smoke_test(url: str, timeout: int = 5) -> dict:
    """run a curl smoke test against a url, returns status and timing"""
    try:
        result = subprocess.run(
            [
                'curl', '-sS', '-o', '/dev/null',
                '-w', '%{http_code}|%{time_total}',
                '--max-time', str(timeout),
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


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command or not is_deploy_command(command):
        sys.exit(0)

    config = load_endpoints()
    defaults = config.get('defaults', {})
    max_time = defaults.get('max_response_time', 2.0)
    default_timeout = defaults.get('timeout', 5)

    service_name = extract_service_name(command)
    endpoints_to_test = []

    if service_name and service_name in config:
        ep = config[service_name]
        endpoints_to_test.append(ep)
    elif service_name:
        # no configured endpoint — try common health paths
        endpoints_to_test.append({
            'url': f'http://127.0.0.1:8080/health',
            'timeout': default_timeout,
        })
    else:
        # test all configured endpoints (except defaults key)
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
        if not url:
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

    # build context report
    lines = [f"deploy smoke test results for: {command[:80]}"]
    for r in results:
        if r['error']:
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
        lines.append("")
        lines.append("WARNING: one or more smoke tests failed — investigate before proceeding")

    context = '\n'.join(lines)
    output = {
        'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': context,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == '__main__':
    main()
