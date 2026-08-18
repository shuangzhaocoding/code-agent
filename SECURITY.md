# Security

Code Agent has **no login**. The agent can read/write the workspace and run a shell.

- Default bind: `127.0.0.1` only.
- Do not publish an unauthenticated instance to the internet.
- API keys are encrypted at rest with a local master key (`~/.code-agent/master.key` or `CODE_AGENT_MASTER_KEY`).
- File tools cannot escape the workspace root.
- Report vulnerabilities privately; do not file public exploit issues.
