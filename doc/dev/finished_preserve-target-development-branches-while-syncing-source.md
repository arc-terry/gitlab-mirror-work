# Preserve target development branches while syncing source

## Question
How can we keep target-only development branches while still synchronizing source branches from upstream?

## Summary
Current mirror behavior uses `git push --mirror`, which deletes refs that do not exist on source. This conflicts with keeping target-only development branches.

## Decisions
- Keep `git push --mirror` semantics for normal refs.
- Preserve only target-only branches under configured prefix:
  - `TARGET_DEV_BRANCH_PREFIX=arc-hsinchu`
  - preserved scope: `refs/heads/arc-hsinchu/*`
- Add deletion confirmation prompt when non-preserved branches would be deleted.

## Pros and cons

### Option A: Prefix-preserve + mirror semantics (selected)
- Pros:
  - Preserves target-only development branches under `arc-hsinchu/*`.
  - Keeps strict mirror behavior for non-preserved refs.
- Cons:
  - Requires clear branch-prefix discipline.

### Option B: Two-repository model
- Pros:
  - Clean separation between strict mirror and development repo.
- Cons:
  - More operational overhead.

### Option C: Namespaced source refs (for example `src/*`)
- Pros:
  - Clear ownership boundary between mirrored and local branches.
- Cons:
  - Workflow complexity for users and tooling.

## Next steps
- Implemented:
  - Add `TARGET_DEV_BRANCH_PREFIX` config.
  - Preserve prefixed target-only branches before `git push --mirror`.
  - Show preserved category in dry-run ref diff output.
  - Prompt Y/N confirmation before deleting non-preserved target refs.
  - Update documentation in README and technical details.
