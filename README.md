# deploy-guard

Deploy safety enforcement for Claude Code sessions.

## What it checks

- **Smoke tests**: after deploy commands, runs HTTP health checks against configured endpoints and reports status/latency
- **Perf regression detection**: after curl/wget/hey/ab/wrk commands, flags response times exceeding the 2s threshold
- **Test gate**: blocks deploy commands if the test suite has not been run in the current session

## Commands

- `/deploy` -- standardised deployment workflow with tests, build, deploy, and health checks
- `/ci` -- scaffold a GitHub Actions CI/CD workflow based on detected project type

## Installation

```
claude plugin marketplace add wrxck/claude-plugins
claude plugin install deploy-guard@wrxck-claude-plugins
```
