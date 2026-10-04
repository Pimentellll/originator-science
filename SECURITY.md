# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately through GitHub:
**Security → Report a vulnerability** on this repository
([direct link](https://github.com/Pimentellll/originator-science/security/advisories/new)).

Include:
- what is affected;
- how to reproduce it;
- the impact you expect.

We aim to acknowledge reports within 7 days. The project is maintained by a small team, so a fix
can take longer.

## Scope

MIRAGE is a research benchmark meant to run locally. Reports we especially want:

- **Leaks of hidden truth.** Any way for a public API route, prompt or public record to reveal
  the simulator's hidden state, or to bypass the token gate on the evaluator-only
  `/benchmarks/*` routes.
- **Credential exposure.** API keys being logged, written to records, or committed.
- **Unsafe file handling.** Paths through which the API or scripts write outside their output
  directory, or overwrite frozen results.

The local demo server is not hardened for exposure to the public internet. Running it that way is
not a supported configuration.

## Supported versions

Only the latest `main` gets security fixes.
