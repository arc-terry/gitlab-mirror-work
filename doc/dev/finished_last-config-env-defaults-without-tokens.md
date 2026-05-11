# Record last configuration excluding tokens

## Question
How can the tool record the previous run configuration without storing token secrets, and reuse it next run?

## Summary
Add a repository-root `.lastconfig.env` file that stores non-secret runtime configuration (`KEY=VALUE`), auto-load it as defaults on startup, and let current environment variables override file values.

## Decisions
- Persist latest non-secret config to `.lastconfig.env` every run.
- Exclude `SRC_TOKEN` and `DST_TOKEN` from both load and write logic.
- Treat `TARGET_DEV_BRANCH_PREFIX` as required config:
  - real prefix enables preservation
  - `NONE` explicitly disables the feature
- Keep `.lastconfig.env` independent from log files.

## Pros and cons

### Pros
- Fast rerun workflow with less repeated env typing.
- Structured and human-readable configuration snapshot.
- Secret safety for token values.

### Cons
- Runtime behavior now depends on local state file presence.
- Users must understand precedence (env overrides file).

## Next steps
- None. Feature and documentation are implemented.
