# /deploy

Standardised deployment workflow that ensures tests pass, builds succeed, and health checks verify the deployment before considering it complete.

## Usage

- `/deploy` -- deploy the current project
- `/deploy <service-name>` -- deploy a specific service

## Steps

1. **Run the test suite** -- execute the project's test suite (npm test, pytest, truewaf_tests, cargo test, etc. as appropriate) and verify all tests pass. If any tests fail, stop and report the failures -- do not proceed with deployment.

2. **Build the project** -- run the appropriate build command (make, npm run build, docker build, docker compose build, etc.). Verify the build succeeds without errors.

3. **Show change summary** -- display a summary of what changed since the last deploy:
   - `git diff --stat HEAD~5..HEAD` or similar to show recent changes
   - list the key files modified and a brief description of changes

4. **Deploy** -- execute the deployment command appropriate for the project:
   - for systemd services: `systemctl restart <service>`
   - for docker: `docker compose up -d`
   - for binaries: `cp build/... /usr/local/bin/...`
   - ask the user to run any commands that require sudo

5. **Run health checks** -- test all affected endpoints using curl:
   - check endpoints from `~/.claude/hooks/deploy_endpoints.json` if available
   - verify HTTP status codes are 2xx/3xx
   - verify response times are under 2 seconds
   - for each endpoint, report: URL, status code, response time, pass/fail

6. **Report results** -- produce a summary:
   - tests: passed/failed count
   - build: success/failure
   - deploy: executed command
   - health checks: pass/fail for each endpoint with response times
   - overall: DEPLOY SUCCEEDED or DEPLOY FAILED

7. **Rollback on failure** -- if any health check fails after deployment:
   - report which checks failed and why
   - suggest rollback steps (e.g. restart previous version, git stash, docker rollback)
   - do NOT automatically rollback without user confirmation
