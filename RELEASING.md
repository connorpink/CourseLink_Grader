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
4. Require the `Release Label` workflow to pass before merging.
5. Prefer squash merges so release history stays clean.

## Release labels

Normal pull requests that target `main` should carry exactly one of these labels:

- `release:patch`
- `release:minor`
- `release:major`
- `release:none`

The `Release Label` workflow validates that exactly one label is present before the PR can merge.
The automated release PR itself uses the `release/next` branch and is excluded from this check.
Create these labels once in the GitHub repository settings so they are available on every PR.

## Release flow

1. Create a feature or fix branch and open a pull request as usual.
2. Add exactly one release label to the PR:
   - `release:patch` for bug fixes and small improvements
   - `release:minor` for backward-compatible features
   - `release:major` for breaking changes
   - `release:none` when no package release should be created
3. Merge the PR into `main` after CI passes.
4. GitHub Actions will scan merged PRs since the last tag and create or update a `release/next` pull request with the correct version bump.
5. Review and merge the generated release PR when you are ready to publish.
6. GitHub Actions will tag the merged release commit and then publish to PyPI from that tag.

The publish workflow only runs on pushed `v*` tags, and it checks that the Git tag matches the package version before uploading.
