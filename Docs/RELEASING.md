# Releasing

This repository now uses a label-driven release flow.
Normal development changes go through pull requests to `main`, and package publishing happens automatically from a generated release PR.

## One-time setup

GitHub:

1. Protect `main`.
2. Require pull requests before merging.
3. Require these checks on PRs to `main`:
   - `Validate (Python 3.10)`
   - `Validate (Python 3.11)`
   - `Validate (Python 3.12)`
   - `Build distributions`
   - `Validate release label`
4. Prefer squash merges so release history stays clean.

PyPI:

1. Open the `courselink-grader` project on PyPI.
2. Go to `Manage` -> `Publishing`.
3. Add a GitHub trusted publisher with:
   - Owner: `connorpink`
   - Repository name: `CourseLink_Grader`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

Release labels:

- `release:patch`
- `release:minor`
- `release:major`
- `release:none`

## Standard flow

1. Create a branch from `main`.
2. Open a pull request to `main`.
3. Add exactly one release label to the PR.
4. Wait for CI and the release-label check to pass.
5. Merge the PR.

What happens next:

- If the label was `release:none`, nothing is published.
- If the label was `release:patch`, `release:minor`, or `release:major`, GitHub Actions creates or updates a `release/next` PR with the version bump.
- Merge `release/next` when you are ready to publish.
- GitHub Actions tags that merge commit and publishes to PyPI from the tag.

## Bootstrap note

`Validate release label` only becomes selectable in branch protection after it has run successfully in the repository.
If it does not appear in GitHub's required-check search yet, open a normal PR first so the workflow can run once.

## Manual fallback

The standard path is the automated release PR flow above.
If GitHub Actions is unavailable and you need to publish from your own machine, `uv publish` supports token-based uploads:

```bash
export UV_PUBLISH_TOKEN='pypi-...'
uv publish --token "$UV_PUBLISH_TOKEN"
```
