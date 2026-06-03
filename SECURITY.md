# Security Policy

OSGE is an early research prototype. The project handles local graph data, platform account metadata, browser sessions, and generated visualization files.

## Supported Versions

Security fixes are handled on the current main development line. There is no long-term support release series yet.

## Reporting a Vulnerability

Do not publish cookies, tokens, raw platform responses, database files, Chromium profiles, or private account data in public issues.

Preferred reporting path:

1. Use GitHub private vulnerability reporting if it is enabled for the repository.
2. If private reporting is not available, open a public issue with a minimal description and no sensitive data.
3. Share reproduction details only after a maintainer provides a private channel.

## Sensitive Data

Do not commit:

- Chromium user profiles
- cookies or session tokens
- platform account private data
- raw platform API responses
- local SQLite databases
- crawl logs
- generated graph exports containing real account data

If sensitive data is committed, remove it from the working tree and repository history before publishing or sharing the repository.

## Scope

In scope:

- local Web service security issues
- data leakage through generated files or logs
- unsafe handling of cookies, tokens, or browser session data
- bugs that bypass OSGE's public-data-only boundary

Out of scope:

- bypassing platform access controls
- scraping private or unauthorized data
- platform anti-abuse circumvention
- attacks against third-party platforms

See `docs/ETHICS.md` for project boundaries and prohibited uses.
