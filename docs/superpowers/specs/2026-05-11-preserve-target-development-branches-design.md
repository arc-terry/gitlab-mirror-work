# Preserve Target Development Branches Design

## Status and provenance

Historical, completed design migrated from the repository's development records.
The filename date comes from the corresponding Git history, not a verified
original design approval date. The original record identifies prefix preservation
as the selected approach; no original approval transcript was reviewed.

## Intent and goals

Keep target-only development branches while synchronizing upstream source refs.
An unrestricted `git push --mirror` deletes target refs absent from the local
mirror, which conflicts with keeping destination development branches.

## Non-goals and constraints

- Keep normal mirror semantics for refs outside the preserved branch namespace.
- Do not preserve every target-only branch or change the development workflow
  to require separate repositories or namespaced source refs.
- Preserve target-only branches, not all branches sharing a prefix regardless
  of whether they also exist on the source.

## Approaches

### Prefix preservation with mirror semantics (selected)

Preserve target-only branches under a configured prefix, such as
`refs/heads/arc-hsinchu/*`, while keeping strict mirroring for other refs.
This fits the existing workflow but requires clear branch-prefix discipline.

### Separate mirror and development repositories

Separates strict mirroring from development cleanly, but adds operational
overhead.

### Namespaced source refs, such as `src/*`

Makes ownership of mirrored and local refs explicit, but adds workflow and
tooling complexity.

## Design decisions

- Configure the preserved namespace through `TARGET_DEV_BRANCH_PREFIX`, for
  example `arc-hsinchu`.
- Preserve only target-only branches under `refs/heads/<prefix>/*` by fetching
  them into the local mirror before `git push --mirror`.
- Show preserved target-only refs as a separate category in the dry-run diff.
- Require deletion confirmation in real runs when non-preserved target refs
  would be deleted, subject to the tool's automatic-confirmation setting.
- Other refs retain ordinary mirror update/deletion behavior.

## Completion record

The original record reports the configuration, preservation fetch, dry-run
category, deletion prompt, and associated documentation as implemented. It
records no remaining implementation tasks and contains no test-run evidence.
This migration does not add retrospective verification or claim a new approval.

This is a historical short design, not an executable implementation plan.
