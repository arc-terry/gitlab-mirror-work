# Group Repository Log Output Design

## Status and provenance

Completed design, migrated from the repository's development records. The user
approved the grouped preview and green headings before implementation. The date
identifies this session's design work, not the migration date.

## Intent and goals

Keep each repository's status, URLs, ref comparison, activity, and result in one
segment so readers do not have to join information across dashed separators.
Display `[MIRROR PROJECT #N]` headings in green on interactive terminals while
keeping saved logs and redirected output free of heading color codes.

## Non-goals and constraints

- Do not change remote operations, configuration, or confirmation behavior.
- Do not rewrite historical logs.
- Add no dependency or color configuration.
- Keep archive command traces at the end of the run with project-number links.
- Do not automatically commit changes.

## Approaches

### Move heading ownership to the project loop (selected)

Emit the heading before project creation/existence checks. Keep subsequent
activity in execution order and remove internal dashed separators. This avoids
buffering, preserves immediate output, and uses the existing logging helper.

### Buffer and rewrite repository output (not selected)

Regroup messages after collecting them. This introduces buffering and rewriting
that are unnecessary for sequential project processing.

## Design decisions and tradeoffs

- The project loop owns one numbered heading per repository, before creation,
  existence, skip, or failure messages.
- Skipped and failed projects also receive numbered segments, so their output
  cannot appear to belong to the previous repository. Project numbers therefore
  include skipped and failed projects.
- The existing `log()` helper colors repository headings only when stdout is a
  terminal. Saved output remains plain text.
- Repository details and activity follow the heading without dashed dividers.
- No remaining design choices or implementation tasks were recorded.

## Completion evidence

These are historical results from implementation, not fresh migration checks:

- Two unittest tests passed, covering terminal and redirected output, plain saved
  logs, and existing/new/skipped/failed project blocks. Before implementation,
  five subcases failed as expected.
- Help/version smoke checks and whitespace checks passed.
- A dry run exited 0: 3 groups, 13 projects, no `[ERROR]` or `[FATAL]` entries.
- Latest and archived logs had no ANSI codes; all 13 repository blocks started
  before existence status and had no dashed dividers.
- Direct execution in `wJ:pY` failed before startup because its shell lacked
  `SRC_TOKEN`. The parent session ran successfully and replayed the resulting
  log with green headings in `wJ:pY`, without transferring secrets.
- Live pushes were not run. No independent review was performed.

This document is a completed design record, not an executable implementation
plan. The original completed checklist is summarized by the evidence above.
