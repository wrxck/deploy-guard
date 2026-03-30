# /ci -- Generate CI/CD Workflow

Scaffold a GitHub Actions CI/CD workflow for the current project. Detect the project type and tooling, then generate an appropriate `.github/workflows/ci.yml`.

## Steps

### 1. Detect Project Type

Check for these files in the current directory (check all in parallel):
- `package.json` -> Node.js project
- `go.mod` -> Go project
- `Cargo.toml` -> Rust project
- `CMakeLists.txt` -> C++ project
- `pyproject.toml` or `setup.py` or `requirements.txt` -> Python project

If multiple are found, the primary is the one with the build system (e.g. CMakeLists.txt over package.json in a mixed repo).

### 2. Detect Test Commands

For Node.js: read `package.json` scripts for `test`, `test:unit`, `test:e2e`, `lint`, `typecheck`, `build`
For Go: check for `*_test.go` files -> `go test ./...`
For Rust: `cargo test`
For C++: check for `tests/` directory, Catch2/gtest in CMakeLists.txt
For Python: check for `pytest.ini`, `pyproject.toml` [tool.pytest], or `tests/` directory

### 3. Detect Infrastructure

- `Dockerfile` -> add Docker build step
- `docker-compose.yml` -> note for deploy step
- `.env.example` -> note env vars needed
- Deployment scripts or Makefile deploy targets

### 4. Generate Workflow

Create `.github/workflows/ci.yml` with these sections:

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # ... project-type-specific setup, build, lint, test steps ...

  docker:
    # only if Dockerfile exists
    needs: build-and-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5

  deploy:
    # manual trigger
    needs: [build-and-test]
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      # project-specific deploy steps
```

#### Node.js template:
- `actions/setup-node@v4` with node version from `.nvmrc` or `engines` field or default to 20
- `npm ci`
- `npm run lint` (if script exists)
- `npm run typecheck` (if script exists)
- `npm test` (if script exists)
- `npm run build` (if script exists)

#### Go template:
- `actions/setup-go@v5` with Go version from `go.mod`
- `go build ./...`
- `golangci-lint` run
- `go test ./...`

#### Rust template:
- `dtolnay/rust-toolchain@stable`
- `cargo fmt -- --check`
- `cargo clippy -- -D warnings`
- `cargo test`

#### C++ template:
- Install build deps
- `cmake -B build -DCMAKE_BUILD_TYPE=Release`
- `cmake --build build`
- `./build/tests/*` if test binary detected

#### Python template:
- `actions/setup-python@v5` with version from `pyproject.toml` or default to 3.12
- Install dependencies
- `ruff check .` or `flake8` (if detected)
- `pytest`

### 5. Present and Confirm

Show the generated workflow YAML to the user with explanations for each section. Ask before writing the file. Highlight:
- What triggers the workflow
- What each step does
- What they may want to customise (secrets, deploy targets, etc.)
