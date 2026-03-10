# Releasing

## Local publish

If you publish from your own machine, `uv publish` will prompt for credentials unless you provide a token.
PyPI no longer accepts account password auth for uploads, so use a token instead.

```bash
export UV_PUBLISH_TOKEN='pypi-...'
uv publish
```

You can also pass the token directly:

```bash
uv publish --token "$UV_PUBLISH_TOKEN"
```

## GitHub Actions publish

This repo includes `.github/workflows/publish.yml`, which is set up for PyPI trusted publishing.
That means GitHub Actions can publish without storing a PyPI token in GitHub Secrets.

GitHub setup:

1. In the repository settings, create an environment named `pypi`.
2. Optionally add required reviewers or branch restrictions to that environment.

PyPI setup:

1. Open the `courselink-grader` project on PyPI.
2. Go to `Manage` -> `Publishing`.
3. Add a GitHub trusted publisher with:
   - Owner: `connorpink`
   - Repository name: `CourseLink_Grader`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

## Standard branch flow

Use `main` as the protected branch and do normal work on short-lived branches:

```bash
git switch -c feature/short-description
```

Suggested conventions:

- `feature/...` for new features
- `fix/...` for bug fixes
- `chore/...` for maintenance or release prep

Recommended GitHub settings:

1. Protect `main`.
2. Require pull requests before merging.
3. Require the `CI` workflow to pass before merging.
4. Prefer squash merges so release history stays clean.

## Release flow

1. Merge the release-ready changes into `main`.
2. Bump the version:

```bash
uv version --bump patch
```

3. Commit the version bump.
4. Tag the exact matching version:

```bash
git tag -a "v$(uv version --short)" -m "Release v$(uv version --short)"
git push origin main --tags
```

5. GitHub Actions will build, smoke test, and publish the package.

The publish workflow checks that the Git tag matches the package version before uploading.

