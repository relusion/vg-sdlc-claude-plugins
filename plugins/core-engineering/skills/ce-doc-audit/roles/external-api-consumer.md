# Role: external-api-consumer

## Goal
Integrate against our public API and get a first successful authenticated call,
working only from the published docs — no access to our source or our people.

## Knows
- General REST / HTTP, JSON, status codes.
- How to use `curl` and read a terminal.
- How to set an environment variable in their own shell.

## Has access to
- A terminal with `curl` and a JSON tool (`jq`).
- One API key we issued them (a scrubbed test key in the sandbox).
- The public documentation only.

## Does NOT know   ← the crux
- Our internal service names, hostnames, or which base URL is "the" base URL.
- Any default that "everyone on the team knows" (rate limits, required headers,
  the auth scheme) unless the doc states it.
- What our error codes mean beyond the HTTP standard.

## Cannot see / access
- Our source repository, internal wikis, Slack, or staging dashboards.
- Environment variables or config that aren't spelled out in the doc.
- Anyone to ask — the doc is the only channel.

## Environment
- macOS or Linux, bash/zsh, `curl` + `jq` preinstalled. No repo checkout, no SDK
  unless the doc tells them to install one (and how).

## Success looks like   ← caps severity
- A documented example request returns the documented response with their key,
  and they understand how to make the next call without guessing. Anything past
  that first successful call (optional endpoints, advanced auth) is after-success.
