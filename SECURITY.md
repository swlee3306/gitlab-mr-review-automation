# Security and data handling

Use synthetic events when evaluating the demo. Do not add credentials, private URLs,
customer source, production logs, or database files to an issue or pull request.

The built-in privacy patterns are illustrative and incomplete. Before adding a live
reviewer, define the permitted data boundary, strengthen scanning, and apply request
and response size/time limits. Never blindly publish model output or treat it as instructions.

Database state is intentionally minimal. No network or external publication adapter
is supplied. A live integration needs authentication, authorization, webhook replay
policy, rate limits and publication reconciliation of its own.

When reporting a defect, provide a minimal synthetic reproduction, expected status
and actual status. Do not submit a real token as evidence.
