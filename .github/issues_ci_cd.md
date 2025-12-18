# Issue: CI/CD Pipeline Implementation

## Overview

This issue covers the implementation of a comprehensive CI/CD pipeline for SentinelRouter using GitHub Actions. The pipeline will ensure code quality, run comprehensive tests, and enable safe deployments to staging and production.

**Created:** December 18, 2025  
**Priority:** High  
**Estimated Time:** 4-6 hours  
**Status:** Planning

---

## Problem Statement

### Current State

The SentinelRouter project currently lacks automated CI/CD pipelines. This results in:

1. **Manual Testing:** Developers must run tests locally before merging, leading to inconsistent validation and potential regression.
2. **No Automated Integration Tests:** Integration tests that require external API keys are not run automatically, making it difficult to catch issues early.
3. **No Staging Deployment:** There is no automated deployment to a staging environment for pre-production validation.
4. **Inconsistent Code Quality:** No automated checks for code formatting, type checking, or unit test coverage.

### Requirements

1. **Pull Request Validation:** Automatically run unit tests, integration tests, code formatting, and type checking on every pull request to `main`.
2. **Release Pipeline:** When code is merged to `main` or a tag is pushed, run comprehensive integration tests and build Docker images.
3. **Staging Deployment:** Provide a workflow to deploy the application to a staging environment for validation before production.
4. **Security and Secrets:** Use GitHub Secrets to securely store API keys and deployment credentials.
5. **Branch Protection:** Enforce that the CI pipeline must pass before merging to `main`.

---

## Architecture Changes

### 1. GitHub Actions Workflows

Three new workflow files will be created in `.github/workflows/`:

#### a) CI - Pull Request Validation (`ci-pull-request.yml`)
- **Trigger:** Pull requests targeting `main`
- **Jobs:**
  - `test`: Runs on Python 3.11 and 3.12, installs dependencies, checks formatting with black, runs static type checking with mypy, runs unit tests.
  - `build-docker`: Builds Docker image to ensure the Dockerfile is valid (depends on `test`).

#### b) Release Integration Pipeline (`release-integration.yml`)
- **Trigger:** Push to `main` and tags `v*`
- **Jobs:**
  - `integration`: Runs comprehensive integration tests (including external API verification) and generates coverage reports.
  - `package`: If triggered by a tag, builds and pushes Docker images to GitHub Container Registry.

#### c) Deploy to Staging (`deploy-staging.yml`)
- **Trigger:** Manual (`workflow_dispatch`) or push to `staging` branch (if exists)
- **Jobs:**
  - `deploy`: Logs into container registry, pulls the specified Docker image, deploys to a staging server via SSH, runs health check, and notifies Slack on success.

### 2. Secrets Configuration

The following secrets must be set in the GitHub repository settings:

- `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` (for integration tests)
- `GITHUB_TOKEN` (automatically provided)
- `STAGING_SSH_KEY`, `STAGING_HOST`, `STAGING_USER` (for staging deployment)
- `SLACK_WEBHOOK_URL` (optional, for notifications)

### 3. Branch Protection Rule

Enable branch protection for `main` requiring:
- The "CI - Pull Request Validation" workflow must pass.
- At least one review (optional).
- No direct pushes (all changes must go through pull requests).

---

## Implementation Plan

### Phase 1: Create Workflow Files (1 hour)

**Step 1.1:** Create directory `.github/workflows/` if it doesn't exist.

**Step 1.2:** Create `ci-pull-request.yml` with the content designed.

**Step 1.3:** Create `release-integration.yml` with the content designed.

**Step 1.4:** Create `deploy-staging.yml` with the content designed.

### Phase 2: Configure Secrets (0.5 hours)

**Step 2.1:** Add the required secrets to the GitHub repository settings (manually via GitHub UI).

### Phase 3: Test Workflows (2 hours)

**Step 3.1:** Trigger the pull request workflow by creating a test PR.

**Step 3.2:** Verify that all steps pass, including unit tests and Docker build.

**Step 3.3:** Merge a test change to `main` to trigger the release pipeline.

**Step 3.4:** Verify integration tests run and coverage is generated.

**Step 3.5:** Test the staging deployment manually (if staging environment is set up).

### Phase 4: Enable Branch Protection (0.5 hours)

**Step 4.1:** Enable branch protection for `main` with the required checks.

### Phase 5: Documentation (0.5 hours)

**Step 5.1:** Update `README.md` to mention the CI/CD pipeline and badge.

**Step 5.2:** Add documentation in `documentation/development/contributing.md` about the workflow.

---

## Testing Plan

### Unit Tests

All existing unit tests must pass in the CI environment. The `ci-pull-request.yml` workflow will run `pytest tests/unit/ -v`.

### Integration Tests

The `release-integration.yml` workflow will run integration tests that may require external API keys. These tests should be marked with `@pytest.mark.integration` and can be skipped if secrets are not available.

### Manual Testing

- Create a pull request and verify that the CI runs.
- Merge a change to `main` and verify that the release pipeline runs.
- Manually trigger the staging deployment and verify the application is deployed.

---

## Acceptance Criteria

### ✅ Pull Request Validation

- [ ] Workflow runs on every pull request to `main`
- [ ] Code formatting checked with black (fail if not formatted)
- [ ] Static type checking with mypy passes
- [ ] Unit tests pass on Python 3.11 and 3.12
- [ ] Docker image builds successfully

### ✅ Release Pipeline

- [ ] Workflow runs on push to `main` and tags
- [ ] Integration tests run (with external API keys)
- [ ] Coverage report generated and uploaded to Codecov (optional)
- [ ] Docker image built and pushed to GitHub Container Registry on tags

### ✅ Staging Deployment

- [ ] Workflow can be triggered manually or by push to `staging`
- [ ] Docker image pulled from registry
- [ ] Application deployed to staging server via SSH
- [ ] Health check passes after deployment
- [ ] Slack notification sent on success (if configured)

### ✅ Branch Protection

- [ ] Branch protection rule enabled for `main`
- [ ] CI must pass before merging
- [ ] Direct pushes to `main` blocked

### ✅ Documentation

- [ ] README includes CI status badge
- [ ] Contributing guidelines updated to mention CI/CD

---

## Rollback Plan

If the CI/CD pipeline causes issues:

1. **Disable Branch Protection:** Temporarily disable branch protection in GitHub repository settings.
2. **Remove Workflow Files:** Delete the workflow files from `.github/workflows/` to stop all automated runs.
3. **Revert Secrets:** Remove the secrets if they are no longer needed.

---

## Timeline

| Phase | Task | Time | Status |
|-------|------|------|--------|
| 1 | Create workflow files | 1h | ⏳ Not Started |
| 2 | Configure secrets | 0.5h | ⏳ Not Started |
| 3 | Test workflows | 2h | ⏳ Not Started |
| 4 | Enable branch protection | 0.5h | ⏳ Not Started |
| 5 | Documentation | 0.5h | ⏳ Not Started |
| **Total** | | **4.5h** | |

---

## Success Metrics

After implementation, the project should have:

1. **Automated Quality Gates:** Every pull request automatically validated for code quality and tests.
2. **Reliable Releases:** Every merge to `main` triggers integration tests and Docker builds.
3. **Safe Deployments:** Staging deployments are automated and health-checked.
4. **Improved Developer Experience:** Developers get immediate feedback on their changes.

---

## Related Issues

- Multi‑Key Support with Per‑Key Rate Limiting (`issue_multiKey.md`)
- Enhanced Routing Decision and Escalation Tracking (`issues_enhancedRoutingDecisionTracking.md`)

---

## Notes

- **Cost:** GitHub Actions provides 2000 free minutes per month for public repositories, which should be sufficient for this project.
- **Security:** Secrets are encrypted and not exposed in logs.
- **Scalability:** The pipeline can be extended later to include production deployments, performance tests, and security scanning.
- **Integration Test Costs:** Running integration tests that call external APIs may incur costs (but the tests are limited to a few calls per run).