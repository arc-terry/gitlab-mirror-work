# Reveal mirror commands in markdown log

> Superseded by: `finished_merge-command-trace-into-single-log-with-project-numbering.md`

## Question
How can we make mirror work reveal executed commands in a markdown log?

## Summary
Initial implementation captured executed command traces and wrote a separate per-run command markdown report under `log/`. A follow-up merged command trace into the same archived run log.

## Initial decisions
- Keep existing plain-text logs (`.lastlog` and `log/*.log`) unchanged.
- Add structured command capture and export (initially to a separate command markdown file).
- Include commands from:
  - generic `run()` helper
  - `run_push_mirror_with_diagnostics()`
  - direct subprocess helpers (for example `ls-remote`, bare repo probe)
- Redact token values in markdown command output.

## Pros and cons

### Pros
- Easier auditing of what mirror actually executed.
- Better human readability for reviews and troubleshooting.
- Maintains backward compatibility with existing log consumers.

### Cons
- Additional file written per run.
- Command capture must stay synchronized with future subprocess call paths.

## Next steps
- None. Implemented and documented in README and technical details.
