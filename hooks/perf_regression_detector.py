#!/usr/bin/env python3
"""
Claude Code PostToolUse hook for Bash commands.
After curl/wget/hey/ab/wrk/autocannon commands, parses response time
and flags if it exceeds the 2s threshold.
"""

import json
import re
import sys


# commands that produce timing/latency output
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
    """check if command is a performance/HTTP test tool"""
    return any(re.search(p, command) for p in PERF_COMMANDS)


def parse_curl_time(output: str) -> float | None:
    """extract time_total from curl -w output"""
    # curl -w '%{time_total}' outputs like: 0.234
    # or with other formats: time_total: 0.234
    m = re.search(r'time_total[:\s]+(\d+\.?\d*)', output)
    if m:
        return float(m.group(1))
    # bare float at end of output (common with -w '%{time_total}')
    m = re.search(r'(\d+\.\d+)\s*$', output.strip())
    if m:
        try:
            val = float(m.group(1))
            # sanity check — should be a reasonable time value
            if 0 < val < 300:
                return val
        except ValueError:
            pass
    return None


def parse_hey_latency(output: str) -> float | None:
    """extract average latency from hey output"""
    # hey outputs: Average: 0.1234 secs
    m = re.search(r'Average:\s+(\d+\.?\d*)\s+secs', output)
    if m:
        return float(m.group(1))
    return None


def parse_ab_latency(output: str) -> float | None:
    """extract mean time per request from ab output"""
    # ab outputs: Time per request: 123.456 [ms] (mean)
    m = re.search(r'Time per request:\s+(\d+\.?\d*)\s+\[ms\].*\(mean\)', output)
    if m:
        return float(m.group(1)) / 1000  # convert ms to seconds
    return None


def parse_wrk_latency(output: str) -> float | None:
    """extract average latency from wrk output"""
    # wrk outputs: Latency   123.45ms  ...
    m = re.search(r'Latency\s+(\d+\.?\d*)(ms|s|us)', output)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        if unit == 'ms':
            return val / 1000
        elif unit == 'us':
            return val / 1_000_000
        else:
            return val
    return None


def extract_latency(command: str, output: str) -> float | None:
    """try to extract latency from command output based on the tool used"""
    if re.search(r'\bcurl\b', command):
        return parse_curl_time(output)
    if re.search(r'\bhey\b', command):
        return parse_hey_latency(output)
    if re.search(r'\bab\b', command):
        return parse_ab_latency(output)
    if re.search(r'\bwrk2?\b', command):
        return parse_wrk_latency(output)
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    command = tool_input.get('command', '')
    tool_result = input_data.get('tool_result', {})
    output = tool_result.get('stdout', '') or tool_result.get('output', '') or str(tool_result)

    if not command or not is_perf_command(command):
        sys.exit(0)

    latency = extract_latency(command, output)

    if latency is None:
        sys.exit(0)

    if latency > THRESHOLD_SECONDS:
        context = (
            f"performance warning: response time {latency:.2f}s exceeds "
            f"{THRESHOLD_SECONDS}s threshold — investigate before proceeding. "
            f"command: {command[:80]}"
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
