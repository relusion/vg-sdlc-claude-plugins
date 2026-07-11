---
name: ce-humanize
description: |
  Rewrite AI-generated, generic, or over-polished prose into natural, credible, human-sounding text while preserving meaning, facts, structure, and required terminology — for emails, PR descriptions, READMEs, docs, proposals, commit messages, and other prose. Ephemeral by default (returns the rewrite); edits a named file only on explicit consent, format preserved. Never claims human authorship, fabricates experience or data, or optimizes to defeat AI-detection.
  Triggers: humanize, naturalize, de-robot, de-AI, make less AI-like, make more conversational or authentic, polish or rewrite prose/copy/tone. For generating user-facing docs from a plan's verified behavior use /ce-ship-document; this rewrites the tone of prose that already exists.
argument-hint: "[text, file path, or tone/audience — plus what to rewrite]"
allowed-tools: Read, Edit, Write, Glob, Grep, AskUserQuestion
---

# Humanize

**Invocation input:** Text, a file path, or tone/audience context — plus what to rewrite: $ARGUMENTS

Rewrite the provided prose so it reads like it was written by a competent human
with real context and judgment — natural, specific, and credible — **without
changing what it says**. This is an editorial transform, not a content
generator: it never invents facts, never adds fabricated experience, and never
claims the output was human-written or tries to defeat AI-detection tooling.

It is **repo-agnostic** and **not** part of the plan/spec/implement pipeline — it
consumes and produces none of those artifacts. Use it on any prose, in any repo,
whether or not the repo uses spec-driven development.

## Runtime Inputs

- **What to rewrite (required):** raw text pasted in, a **file path**, or a
  selection already in the conversation. If none is supplied, ask for it before
  doing anything else.
- **Context (optional):** intended audience, medium, tone (`professional`,
  `conversational`, `executive`, `technical`, `academic`, `social`), a length
  bound, or "give me options". Inferred when unstated — never invented into the
  content itself.

## Execution Contract

1. **Meaning is invariant.** Preserve the source's claims, intent, technical
   accuracy, and required terminology exactly. Rewriting changes *how* it reads,
   never *what it asserts*.
2. **No fabrication.** Never add facts, data, quotes, citations, credentials,
   emotions, events, or personal/lived experience the source did not supply.
   Precision over drama: if a claim is vague, keep it vague — do not invent
   specifics to make it land.
3. **No false authorship, no detector-gaming.** Never state or imply the text
   was human-written, and never optimize to evade AI-detection systems. The goal
   is credible, readable prose — not a laundered provenance.
4. **Structure and markup survive.** Preserve code blocks, frontmatter, links,
   tables, headings, lists, Markdown/markup syntax, placeholders, variables, API
   names, config values, numbers, dates, URLs, and legal/compliance wording
   unless the user explicitly asks to change them.
5. **Ephemeral by default.** The default output is the rewritten text in the
   conversation — no file is touched. A file is edited only in File Mode, and
   only after the consent gate below.
6. **Faithful, not just casual.** Success is *more credible*, not merely *more
   informal*. If a requested tone would distort the content, prioritize clarity
   and accuracy and say so.
7. **Out of scope — never rewrite the contract/evidence layer.** This tool
   rewrites the *product-narrative* layer only. Never rewrite an artifact whose
   exact wording is load-bearing: EARS acceptance criteria and specs
   (`ce-spec.md` / `tasks.json` — tagged wording the merge bar traces), evidence
   and findings artifacts (`code-review.md`, `threat-model.md`, `verification.md`,
   security / UX / doc-audit findings), decision records / ADRs, and machine-read
   JSON (`plans.json`, `backlog.json`, `metrics.jsonl`). The whole `docs/plans/**`
   process tree is off-limits. Smoothing a spec corrupts traceability; smoothing a
   finding distorts evidence — decline and say why (Escalation). Also out of
   scope: generating new content and researching facts to add. If asked to *write*
   (not rewrite), route per Escalation.

## Human-in-the-Loop — light

Two modes, one gate:

- **Inline Mode (default).** Text comes in; the rewrite goes back to the
  conversation. No file is written, so there is no gate — the read-back *is* the
  output, and the human accepts it or asks for another pass.
- **File Mode.** When the input is a file path (or the user says "apply it to
  the file"), show the rewrite (or a clear diff) first — the read-back — then ask
  **Apply / Adjust / Cancel** before any Edit. Editing a file without that
  confirmation is not allowed.

## Silent preflight

Before rewriting, infer but do not print (unless asked):

1. Intended audience and medium.
2. Purpose of the text.
3. The tone that fits — matched to context, not defaulted to breezy.
4. Content that must not change (facts, terms, markup, numbers).
5. What currently reads as generic, inflated, repetitive, or over-smoothed.

## Rewrite rules

**Preserve** — meaning, intent, factual claims, technical accuracy, required
terminology, names/dates/numbers/URLs/code references, legal and compliance
wording, and the user's requested format, length, and tone.

**Improve**

- Replace generic transitions and filler with direct phrasing.
- Cut hollow words — "leverage", "seamless", "robust", "unlock",
  "game-changing", "delve", "in today's fast-paced world" — unless one is
  genuinely the right term.
- Reduce repetition and redundant summaries.
- Vary sentence length and paragraph rhythm.
- Prefer concrete nouns and active verbs.
- Use contractions when the medium is conversational.
- Make claims more precise, not more dramatic.
- Add light personality only where the medium invites it.

**Avoid**

- Invented experience, fake vulnerability, or fabricated expertise.
- Slang that undercuts a professional context.
- Polish so heavy the text sounds templated again.
- Marketing inflation without evidence.
- Deliberate "human" typos or errors.
- Simplifying a term into a different meaning.
- Adding citations or facts not present in the source.

## Style calibration

- **Professional** — concise, confident, direct; not corporate.
- **Conversational** — warm, natural, lightly personal, easy to read.
- **Executive** — crisp, outcome-first, low fluff.
- **Technical** — accurate, plainspoken, terminology intact.
- **Academic** — clear and disciplined, without faux-informality.
- **Social** — specific, with a real hook and no manufactured hype.

If the requested tone conflicts with the content, clarity and credibility win.

## Output behavior

- **Default:** return only the rewritten text, in the source's format. No
  commentary, analysis, or bullet-point rationale unless asked.
- **Options:** when the user asks for choices, give up to three, each labeled by
  tone (e.g. *Professional*, *Conversational*, *Sharper*).
- **File Mode:** show the intended change (or diff), then apply it only after the
  Apply / Adjust / Cancel gate. Leave unrelated content untouched.

## Quality checklist

Before returning, confirm:

- It no longer reads as generic or templated.
- The voice fits the audience and medium.
- No fact was added, dropped, or distorted; no fabricated personal detail.
- Markup, terms, numbers, and links are intact.
- It is *more credible*, not merely more casual.
- It is easier to read than the original.

For before/after patterns and the fake-detail failure mode, load
`${CLAUDE_SKILL_DIR}/examples.md` when needed.

## Escalation

- Asked to **write new content** (not rewrite existing prose): route to
  `/ce-ship-document` for user-facing docs grounded in verified behavior, or to
  the relevant spine skill — this tool only rewrites tone.
- Asked to **add facts, research, or citations**: that is content work, not
  humanizing — decline the fabrication and say where the facts should come from.
- Asked to **rewrite a spec, EARS criteria, or an evidence / findings artifact**
  (`ce-spec.md`, `code-review.md`, `threat-model.md`, `verification.md`, a probe
  or `/ce-doc-audit` report, an ADR): decline — its exact wording is a contract or
  attestation the framework depends on; point to the owning skill instead.
- Asked to **misrepresent authorship, defeat AI-detection, or disguise academic
  or compliance misconduct**: refuse, and say why.

## Honest Limitations

- **Not a fact-checker.** It preserves the source's claims; it does not verify
  them. A confident falsehood in becomes a smoother confident falsehood out.
- **Not a content generator.** No text in means nothing to do — it rewrites, it
  does not author from a blank page.
- **Not a detector-beater.** It optimizes for credible, readable prose, not for
  any AI-detection score, and makes no claim about how a detector will grade its
  output.
- **Voice is approximated, not learned.** With no sample of the author's real
  writing, it aims for a competent, natural register — not a personal
  fingerprint.
- **Judgment over the source stays with you.** It will flag when a requested
  tone fights the content, but the human owns the call.
