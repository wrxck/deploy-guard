#!/usr/bin/env python3
"""
Claude Code PostToolUse hook (advisory).
After curl/wget/hey/ab/wrk/autocannon commands, parses response time
and flags if it exceeds the 2s threshold.
"""

import json
import re
import sys


PERF_COMMANDS = [
    r'\bcurl\b',
    r'\bwget\b',
    r'\bhey\b',
    r'\bab\b',
    r'\bautocannon\b',
    r'\bwrk\b',
    r'\bwrk2\b',
]

THRESHOLD_SECONDS = 2.0


def is_perf_command(command: str) -> bool:
    return any(re.search(p, command) for p in PERF_COMMANDS)


def parse_curl_time(output: str):
    m = re.search(r'time_total[:\s=]+(\d+\.?\d*)', output)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = re.search(r'time=(\d+\.?\d*)', output)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = re.search(r'\|(\d+\.\d+)\s*$', output.strip())
    if m:
        try:
            val = float(m.group(1))
            if 0 < val < 300:
                return val
        except ValueError:
            pass
    m = re.search(r'^(\d+\.\d+)\s*$', output.strip())
    if m:
        try:
            val = float(m.group(1))
            if 0 < val < 300:
                return val
        except ValueError:
            pass
    return None


def parse_hey_latency(output: str):
    m = re.search(r'Average:\s+(\d+\.?\d*)\s+secs', output)
    if m:
        return float(m.group(1))
    return None


def parse_ab_latency(output: str):
    m = re.search(r'Time per request:\s+(\d+\.?\d*)\s+\[ms\].*\(mean\)', output)
    if m:
        return float(m.group(1)) / 1000
    return None


def parse_wrk_latency(output: str):
    m = re.search(r'Latency\s+(\d+\.?\d*)(ms|s|us)', output)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        if unit == 'ms':
            return val / 1000
        elif unit == 'us':
            return val / 1_000_000
        return val
    return None


def extract_latency(command: str, output: str):
    if re.search(r'\bcurl\b', command):
        return parse_curl_time(output)
    if re.search(r'\bhey\b', command):
        return parse_hey_latency(output)
    if re.search(r'\bab\b', command):
        return parse_ab_latency(output)
    if re.search(r'\bwrk2?\b', command):
        return parse_wrk_latency(output)
    return None


def get_output(input_data: dict) -> str:
    for key in ('tool_response', 'tool_result'):
        node = input_data.get(key)
        if isinstance(node, dict):
            out = node.get('stdout') or node.get('output') or ''
            if out:
                print(f'perf_regression_detector: read output from {key!r}', file=sys.stderr)
                return out
            if node:
                return str(node)
        elif isinstance(node, str) and node:
            return node
    return ''


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = input_data.get('tool_input', {}) or {}
    command = tool_input.get('command', '') or ''
    output = get_output(input_data)

    if not command or not is_perf_command(command):
        sys.exit(0)

    latency = extract_latency(command, output)
    if latency is None:
        sys.exit(0)

    if latency > THRESHOLD_SECONDS:
        context = (
            f'performance warning: response time {latency:.2f}s exceeds '
            f'{THRESHOLD_SECONDS}s threshold — investigate before proceeding. '
            f'command: {command[:80]}'
        )
        output_data = {
            'hookSpecificOutput': {
                'hookEventName': 'PostToolUse',
                'additionalContext': context,
            }
        }
        print(json.dumps(output_data))

    sys.exit(0)


if __name__ == '__main__':
    main()
