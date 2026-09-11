# Contributing

Start with the README and reproduce the behavior using synthetic data. Small bug fixes, missing regression tests and clearer setup instructions are welcome.

## Local verification

```sh
python3 -m unittest discover -s tests -v
```

These commands do not prove production readiness. Tests that require a provider, database, network device or credentials must be explicitly agreed and run only in an authorized test environment.

## Pull requests

- Explain the observed problem, expected behavior and smallest proposed change.
- Include a reproducible test or example and the exact verification command.
- Keep credentials, real inventories, customer information and private source out of code, logs and screenshots.
- Distinguish an implemented behavior from a future proposal; do not add unsupported benchmark or reliability claims.
- This repository is licensed under the [MIT License](LICENSE). Preserve its copyright and permission notice when redistributing code.

For a suspected vulnerability, do not post a live token or exploit against an existing service in a public issue. Use GitHub private vulnerability reporting if enabled; otherwise ask the maintainer for a private contact without including sensitive details.
