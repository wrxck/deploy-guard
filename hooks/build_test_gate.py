#!/usr/bin/env python3
"""
Claude Code PreToolUse hook for Bash commands.
Blocks deploy commands if the test suite hasn't been run in this session.
Tracks test runs via a temp file keyed by session ID.
"""

import json
import os
import re
import sys
import time


STATE_DIR = os.path.expanduser('~/.claude/hooks')

# commands that count as "running tests"
TEST_PATTERNS = [
    r'\bnpm\s+test\b',
    r'\bnpm\s+run\s+test\b',
    r'\byarn\s+test\b',
    r'\bpnpm\s+test\b',
    r'\bpytest\b',
    r'\bpython\s+-m\s+pytest\b',
    r'\btruewaf_tests\b',
    r'\bjest\b',
    r'\bvitest\b',
    r'\bcargo\s+test\b',
    r'\bgo\s+test\b',
    r'\bmake\s+test\b',
    r'\bctest\b',
]

# commands that count as "deploying"
DEPLOY_PATTERNS = [
    r'\bsystemctl\s+(start|restart)\b',
    r'\bdocker\s+compose\s+up\b',
    r'\bdocker\s+restart\b',
    r'\bcp\s+.*\s+/usr/local/bin/',
]

# infrastructure/production services — exempt from the test gate when restarting
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
    """get the path to the session state file"""
    return os.path.join(STATE_DIR, f'.last_test_run_{session_id}')


def is_test_command(command: str) -> bool:
    """check if command runs a test suite"""
    return any(re.search(p, command) for p in TEST_PATTERNS)


def is_deploy_command(command: str) -> bool:
    """check if command is a deploy action"""
    return any(re.search(p, command) for p in DEPLOY_PATTERNS)


def is_exempt_service(command: str) -> bool:
    """check if command targets a service with no test suite"""
    return any(svc in command for svc in NO_TEST_SERVICES)


def record_test_run(session_id: str):
    """record that tests were run in this session"""
    state_file = get_state_file(session_id)
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, 'w') as f:
        f.write(str(time.time()))


def tests_were_run(session_id: str) -> bool:
    """check if tests were run in this session"""
    state_file = get_state_file(session_id)
    return os.path.exists(state_file)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    command = tool_input.get('command', '')
    session_id = input_data.get('session_id', 'unknown')

    if not command:
        sys.exit(0)

    # if this is a test command, record it and allow
    if is_test_command(command):
        record_test_run(session_id)
        sys.exit(0)

    # if this is a deploy command, check if tests were run
    if is_deploy_command(command):
        if is_exempt_service(command):
            sys.exit(0)
        if not tests_were_run(session_id):
            print("BLOCKED: test suite not run before deploy", file=sys.stderr)
            print("", file=sys.stderr)
            print("  you must run the test suite before deploying.", file=sys.stderr)
            print("  run the project's tests first, then retry the deploy.", file=sys.stderr)
            print("", file=sys.stderr)
            print(f"  blocked command: {command}", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == '__main__':
    main()
