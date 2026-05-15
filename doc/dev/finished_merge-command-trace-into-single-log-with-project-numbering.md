# Merge command trace into one log with project numbering

## Question
How can we merge command trace output into one run log file and number each mirror project?

## Summary
Command trace output is now appended into the same archived run log (`log/*.log`) instead of a separate commands markdown file. Mirror project operations are numbered and command entries include that project number.

## Decisions
- Keep one archived log file per run:
  - `log/<mmddyyyy>_<HHMMSS>_<RUN|DRYRUN>.log`
- Append a `COMMAND TRACE` section into that same file.
- Number mirror projects sequentially (`#1`, `#2`, ...).
- Tag each captured command entry with project number/target where applicable.

## Pros and cons

### Pros
- Single-file run audit (timeline + command trace together).
- Easier correlation between command lines and project-specific mirror actions.

### Cons
- Archived log files become longer.
- Command trace grouping depends on command capture coverage.

## Next steps
- None. Implemented and documented.
