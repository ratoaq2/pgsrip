---
name: release
description: Release a new pgsrip version to PyPI through a GitHub release, with clean release notes. Use when the user asks to release, publish, tag, or bump the version.
---

# Release

A GitHub release starts the `publish.yml` workflow. It publishes to PyPI. You cannot undo a publish.

## Steps

1. Be on an up-to-date `main` with a clean tree. `bash scripts/test.sh` must pass.
2. Find the version in `pyproject.toml` and the last tag (`git describe --tags --abbrev=0`). Propose the
   new version from the changes since the last tag. The tag has no `v` prefix (`0.2.0`), unless the
   existing tags have one.
3. Update the version. In `CHANGELOG.md`, change `## Unreleased` to the version and the date. Commit
   with `chore: release <version>` through a PR.
4. Generate the notes:

   ```bash
   gh api repos/{owner}/{repo}/releases/generate-notes -f tag_name=<tag> -f target_commitish=main --jq .body > notes.md
   ```

5. Edit `notes.md`:
   - Remove the "What's Changed" lines for PRs from `dependabot[bot]` or from `dependabot/` branches.
   - Remove the "New Contributors" lines for `dependabot[bot]` and for the repository owner.
   - Remove each section that is then empty, with its heading.
6. **Show the tag, the target branch, and the notes to the user. Wait for approval.**
7. Run `gh release create <tag> --target main --title <tag> --notes-file notes.md`.
8. Check the `publish.yml` run: `gh run list --workflow publish.yml --limit 1`.
9. After the publish, the project sets the next development version (`chore: back to development`).
