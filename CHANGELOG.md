# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0] - 2026-05-29

### Added

- **GitLab nested group mirroring**: Mirror entire group hierarchies including
  all subgroups and projects from one GitLab instance to another.
- **Persistent local bare cache**: Reuse local bare repositories under
  `repositories_mirror-use/` for incremental sync — only fetch new objects.
- **Config persistence**: Automatically load defaults from `.lastconfig.env`
  and save non-secret settings after each run.
- **Target branch preservation**: Use `TARGET_DEV_BRANCH_PREFIX` to preserve
  target-only branches (e.g., `arc-hsinchu/*`) during mirror push.
- **Dry-run mode**: Safe default (`DRY_RUN=true`) that previews changes
  without modifying the target.
- **Ref diff report**: Dry-run shows per-project ref diff (refs to create,
  update, or delete) so you can see exactly what is not yet mirrored.
- **Run logging**: Latest output written to `.lastlog`; archived logs saved
  under `log/` with timestamp and run mode in filename.
- **Command trace**: Executed mirror commands appended to archived log files
  with project numbering for easy tracing.
- **Help flag**: Run `python3 mirror.py --help` to see usage without
  requiring environment variables.
- **History rewrite troubleshooting**: Detailed diagnostics and debug commands
  when `git push --mirror` is rejected.
- **Group visibility clamping**: Automatically clamp subgroup visibility to
  parent visibility to avoid invalid GitLab combinations.
