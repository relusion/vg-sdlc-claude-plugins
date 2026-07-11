# Sec-Probe Module — CLI (console apps)

Probe content for **CLI / console** targets. Loaded by the `/ce-probe-sec` spine
(`SKILL.md`) at Stage 0 when the target is a binary or command. The spine owns the
arc, evidence model, triage, and report; this module owns the consent-gate choice,
the sandbox model, tool detection, and the probe taxonomy.

> **The highest-risk module.** CLI probing *executes a binary with adversarial
> input on the local machine.* The sandbox is the safety net; the spine's
> Non-Destructive PoC rule is the belt. Neither is optional.

## Consent gate

**Gate B — Local-Execution Sandbox** (defined in the spine): binary identity →
sandbox confirmation → authorization. Never run as root. Never against real data.

## Preconditions

- The binary / command is identified and runnable.
- A **sandbox mechanism** is available:
  - **Preferred — container** (docker/podman): no network, read-only mounts except a throwaway workdir, non-root, resource-limited.
  - **Fallback — constrained subprocess:** `ulimit -t` (CPU), `-v` (memory), `-f` (file size), `-u` (max procs — stops fork bombs); fresh temp CWD; scrubbed env (drop real secrets); `timeout` wrapper. **Weaker isolation — the human acknowledges at Gate B Q2.**
  - If neither can be established safely → **stop**.
- Optional tools detected: `radamsa` (input mutation) · `strace` / `ltrace` (syscall observation) · `AFL++` / `libFuzzer` (if a fuzz harness exists). Report what's available.

## Stage 1 — Reconnaissance (`recon` tier — no adversarial input)

Run the binary only in safe, read-only ways (`--help`, `--version`); inspect, don't attack.

| Probe | What it checks | CWE |
|---|---|---|
| Arg-surface map | `--help` / subcommands → which args take files, which shell out | — |
| Secrets via argv | secrets passed as args (visible in `ps`) | CWE-214 |
| Privilege posture | setuid bit; requires / escalates privilege | CWE-250 |
| Temp-file handling | predictable / insecure temp-file creation | CWE-377 |
| Terminal output | emits raw bytes → escape-sequence injection risk | CWE-150 |
| Config reads | reads config from cwd/home (overridable, injectable) | CWE-426 |

Findings here are state `passive`.

## Stage 2 — Smell-test (one opt-in)

Single small adversarial inputs, sandboxed.

| Probe | Catches | State | CWE |
|---|---|---|---|
| Argument / option injection | shell metacharacters or `--flag` smuggled via args | suspected | CWE-88 |
| Path traversal via file args | `../../etc/passwd`-style | suspected | CWE-22 |
| Env-var injection | `LD_PRELOAD`, `IFS`, `PATH` manipulation | suspected | CWE-426 / CWE-427 |
| Format string | `%s%n` in args | suspected | CWE-134 |
| Symlink following | a file arg points at a symlink | suspected | CWE-59 |

## Stage 2 — Active exploit (per-category opt-in)

Non-destructive PoC, sandboxed. Confirmation via **timing**, **read-only sentinel
disclosure**, or **controlled crash** — never destructive payloads.

| Category | PoC technique | State | CWE |
|---|---|---|---|
| Command injection | `; sleep 5` in a shelling-out arg → timing delay | confirmed on delay | CWE-78 |
| Path traversal | read a sentinel file placed outside the sandbox CWD | confirmed on disclosure | CWE-22 |
| Option injection | `--output=<sandbox-sentinel>` redirection | confirmed on write to sentinel | CWE-88 |
| Parse / buffer crash | `radamsa`-mutated input → segfault / overflow (the sandboxed process dies — harmless to the host) | confirmed on crash | CWE-120 / CWE-787 |
| Env preload / privesc | `LD_PRELOAD` a benign no-op lib; observe load via `strace` | confirmed on load | CWE-426 |
| TOCTOU / symlink temp | race a predictable temp path | usually **suspected** (hard to confirm non-destructively) | CWE-367 |
| Insecure deserialization | if it parses serialized input, feed a benign marker object | confirmed on marker effect | CWE-502 |

Use `strace` / `ltrace` to observe what each probe actually triggers — an
unexpected `exec`, an `open` outside the sandbox CWD, or a network syscall is often
the evidence itself.

## Honest limitations (CLI)

- **AI-driven CLI fuzzing is shallow** vs coverage-guided fuzzers (AFL++, libFuzzer). For depth, write a harness and run those; this module is a first cut.
- **Isolation is only as strong as the mechanism** — container > ulimit-subprocess. The fallback's weaker isolation is acknowledged at Gate B Q2.
- **Unreachable surfaces:** interactive prompts, GUI sub-processes, and anything requiring real credentials/network the sandbox withholds.
- **Binary-only** limits source-level analysis — pair with `/ce-review` for the code side.
- **Destructive-only classes** (e.g. some TOCTOU) are reported `suspected`, not attempted.
