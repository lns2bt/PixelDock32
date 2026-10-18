# Repository conventions

- Use English for documentation, source comments, UI text, tests, commit messages,
  pull requests, issues, and release notes. Conversation with the maintainer may
  remain in German. Do not rewrite Git history or translate saved user content.
- Back up live Raspberry Pi settings, database, mapping, and assets before deployment.
  Stage substantial updates in a separate directory and retain a rollback path.
- Run mutating browser smoke tests only against `scripts/ui-test-server.py`, never
  against the physical display. Passive production checks must not change settings.
- Sleep policy takes precedence over modules and previews. Never wake the display
  implicitly. Preserve user schedules and day brightness during deployments.
