---
name: ce-ask
description: |
  Answer questions about any code repository — locate code, trace flow, explain rationale, find callers — with structured, file-cited answers that stage the relevant files into the conversation. Ephemeral; writes nothing.
  Triggers: ask how/where/why about a codebase. For a misbehaving running component use /core-engineering:ce-debug — ask answers questions, it does not investigate symptoms.
argument-hint: "[question]"
allowed-tools: Read, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Ask

**Invocation input:** Question: $ARGUMENTS


Answer a developer question about this repository with **grounded, cited answers**
that also load the relevant files into the conversation so follow-up discussion
stays productive.

This tool is **read-only** and **repo-agnostic** — it assumes nothing about the
codebase's structure or conventions. It is **not** part of the plan/spec/implement
pipeline; it does not consume or produce any of those artifacts. Use it for code
Q&A whether the repo uses spec-driven development or not.

## Runtime Inputs

- **Question (required):** a question about the codebase. Examples:
  - *Where is the User model defined?*
  - *How does authentication work?*
  - *Why does the order flow use a queue here?*
  - *What happens if the payment provider returns 500?*
  - *Where would I add a new API endpoint?*
  - *What calls `processOrder`?*
- **The repository:** the current working directory.

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-ask` — this session writes nothing, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Two-phase.** Scope first (cheap search — grep, glob, symbol search), then read only the relevant files. Never bulk-read.
2. **Every factual claim cites `file:line`** (or a small range). No citation, no claim.
3. **Show code over paraphrasing it.** Quote 1–5 lines inline when a short snippet captures the point better than prose.
4. **Honest about uncertainty.** Anything not directly evidenced in the code goes under *Known unknowns*. Do not paper over gaps.
5. **No fabrication.** If a file or symbol isn't found, say so; never invent paths.
6. **Read-only.** No commits, no edits, no writes. The output is the conversation answer; the side effect is that the relevant files are now in the session's context.
7. **Repo-agnostic.** Don't assume language, framework, or layout — detect.
8. **Out of scope:** the plan/spec/implement/verify artifacts under `docs/plans/`. Treat them as ordinary docs if they happen to appear via search; do not seek them out. This tool's job is code Q&A.

## Question Types

Adapt the scoping strategy to the question's shape:

| Type | Example | Strategy |
|---|---|---|
| **Location** | "Where is X defined?" | Symbol/grep search for the name; return `file:line` |
| **Flow** | "How does X work?" | Find entry points; trace calls through 3–8 files |
| **Rationale** | "Why is it built this way?" | Read comments, tests, and `git log/blame` on the relevant lines; flag explicitly if no rationale is recoverable from the artefacts |
| **Failure mode** | "What happens when X fails?" | Find error handling, exception types, fallbacks, failure-case tests |
| **Convention / Placement** | "Where would I add a new W?" | Find existing examples of W; identify the pattern |
| **Impact / Callers** | "What uses Y?" | Reverse search — callers, imports, references |

Most questions fit one type cleanly; some need a combination.

## Workflow

### 1. Parse the question

Identify the question type and the subject (name, symbol, behaviour, or concern
the question is about). If the question is genuinely too vague to act on, ask
*one* short clarifying question before searching.

### 2. Scope — find relevant files (cheap)

Use the strategy for the question type. Prefer:

- **Symbol search** (declaration of a function/type/class) when the question names a specific identifier.
- **Grep** for keywords, error messages, or string literals.
- **Glob** for files matching a known pattern (`*.test.*`, `Dockerfile`, etc.).
- **Entry-point sniffing** for *flow* questions — `routes/`, `cmd/`, `main.*`, `index.*`, HTTP framework decorators, CLI dispatch tables.
- **`git log`/`git blame`** for *rationale* questions, on the specific lines once identified.

Aim for **3–8 candidate files**. Stop scoping when you have enough.

### 3. Read selectively

Read only the candidate files (and only the relevant ranges of large files).
Don't load whole large files just to skim. Index → detail.

### 4. Answer — the structured output

Always use this shape, exactly:

````markdown
**TL;DR:** <one paragraph, ≤ 3 sentences, the headline answer>

**Key files**
- `path/to/file.ts:42-68` — <what this file contributes>
- `path/to/other.py:15` — <what this contributes>

**How it works**

<step-by-step, each factual claim cited inline like (`file.ts:42`)>

<quote short code snippets inline when they're load-bearing>

**Known unknowns**

- <each uncertainty, named with the file or area where evidence is missing>
- _None_ if you genuinely have no uncertainty (rare for non-trivial questions)
````

The **TL;DR** and **Key files** sections are mandatory. **How it works** and
**Known unknowns** appear when the question merits them — a one-line "Where is X?"
answer is also fine.

### 5. Stage the context

The files you read are now in the conversation. The user's follow-up questions in
this session can reference them without re-discovery. Do not save the answer to
disk; it is ephemeral.

## Honesty norms

- **If the codebase does not contain the answer, say so.** "I searched X, Y, Z and found no implementation of this — it may not exist here, or it may be named differently. Do you know more?"
- **Ambiguity:** if two files seem to do the same thing, name both and flag it.
- **Dead code:** if a symbol has no callers, say so — that's relevant context.
- **Shallow read:** if you read only the happy path, offer: "I summarised the happy path; want the error/edge cases too?"
- **Stale evidence:** if a comment contradicts current behaviour, prefer the code and flag the contradiction.

## Escalation

If the answer reveals a change request, route instead of acting: `/core-engineering:ce-impact` for
blast radius, `/core-engineering:ce-patch` for a genuinely small fix, `/core-engineering:ce-plan` for structural work,
or `/core-engineering:ce-debug` for a misbehaving component. This skill remains read-only and
ephemeral.

## Honest Limitations

- Not a planning tool — use `/core-engineering:ce-plan`.
- Not a specification tool — use `/core-engineering:ce-spec`.
- Not a code-modification tool — it is read-only; the `/core-engineering:ce-ask` skill's `allowed-tools` deliberately exclude `Write` and `Edit`.
- Not persistent memory — each invocation reads what's there *now*.
