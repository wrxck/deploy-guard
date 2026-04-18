#!/usr/bin/env python3
"""
Claude Code hooks for deploy/test gating.
PreToolUse: block deploy commands if no successful test run is recorded
or if the last successful run is older than STALE_MINUTES.
PostToolUse: record a successful test run only if exit code was 0.
Fails open (exit 0) on parse errors — advisory, not blocking when unparseable.
"""

import json
import os
import re
import sys
import time


STATE_DIR = os.path.expanduser('~/.claude/hooks')
STALE_MINUTES = 30

TEST_PATTERNS = [
    r'npm\s+test\b',
    r'npm\s+run\s+test\b',
    r'yarn\s+test\b',
    r'pnpm\s+test\b',
    r'pytest\b',
    r'python\s+-m\s+pytest\b',
    r'python3\s+-m\s+pytest\b',
    r'truewaf_tests\b',
    r'jest\b',
    r'vitest\b',
    r'cargo\s+test\b',
    r'go\s+test\b',
    r'make\s+test\b',
    r'ctest\b',
    r'bun\s+test\b',
    r'rspec\b',
    r'mocha\b',
]

TEST_START_RE = re.compile(
    r'(?:^|[;&|]|&&|\|\|)\s*'
    r'(?:[A-Z_][\w]*=\S+\s+)*'
    r'(?:' + '|'.join(TEST_PATTERNS) + r')'
)

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

NO_TEST_SERVICES = [
    'abmanandvan',
    'brandify',
    'devilcat',
    'docker-databases',
    'heskethwebdesign-react',
    'hga',
    'image-merger',
    'leelas-ladybirds',
    'macpool',
    'matthesketh-pro',
    'moltbook-stats',
    'natures-art',
    'nlcgroup',
    'we-teach-academy',
    'zmb',
]


def get_state_file(session_id: str) -> str:
    return os.path.join(STATE_DIR, f'.last_test_run_{session_id}')


def is_test_command(command: str) -> bool:
    return bool(TEST_START_RE.search(command))


def is_deploy_command(command: str) -> bool:
    return bool(DEPLOY_RE.search(command))


def is_exempt_service(command: str) -> bool:
    return any(re.search(rf'\b{re.escape(svc)}\b', command) for svc in NO_TEST_SERVICES)


def record_test_run(session_id: str):
    state_file = get_state_file(session_id)
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, 'w') as f:
        f.write(str(time.time()))


def tests_were_run_recently(session_id: str) -> bool:
    state_file = get_state_file(session_id)
    if not os.path.exists(state_file):
        return False
    try:
        mtime = os.path.getmtime(state_file)
    except OSError:
        return False
    age_minutes = (time.time() - mtime) / 60.0
    return age_minutes <= STALE_MINUTES


def get_exit_code(input_data: dict):
    for key in ('tool_response', 'tool_result'):
        node = input_data.get(key)
        if isinstance(node, dict):
            for code_key in ('exit_code', 'exitCode', 'returncode', 'code'):
                if code_key in node:
                    try:
                        return int(node[code_key])
                    except (TypeError, ValueError):
                        continue
    return None


def pre_tool_use(input_data: dict):
    tool_input = input_data.get('tool_input', {}) or {}
    command = tool_input.get('command', '') or ''
    session_id = input_data.get('session_id', 'unknown')

    if not command:
        sys.exit(0)

    if not is_deploy_command(command):
        sys.exit(0)

    if is_exempt_service(command):
        sys.exit(0)

    if tests_were_run_recently(session_id):
        sys.exit(0)

    print('BLOCKED: test suite not run before deploy', file=sys.stderr)
    print('', file=sys.stderr)
    print('  you must run the project test suite (and have it pass)', file=sys.stderr)
    print(f'  within the last {STALE_MINUTES} minutes before deploying.', file=sys.stderr)
    print('', file=sys.stderr)
    print(f'  blocked command: {command}', file=sys.stderr)
    sys.exit(2)


def post_tool_use(input_data: dict):
    tool_input = input_data.get('tool_input', {}) or {}
    command = tool_input.get('command', '') or ''
    session_id = input_data.get('session_id', 'unknown')

    if not command or not is_test_command(command):
        sys.exit(0)

    exit_code = get_exit_code(input_data)
    if exit_code is not None and exit_code != 0:
        sys.exit(0)

    record_test_run(session_id)
    sys.exit(0)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    event = input_data.get('hook_event_name') or ''
    if event == 'PostToolUse':
        post_tool_use(input_data)
    else:
        pre_tool_use(input_data)


if __name__ == '__main__':
    main()
