# Sec-Probe Module — HTTP (web / API)

Probe content for **web and API** targets. Loaded by the `/core-engineering:ce-probe-sec` spine
(`SKILL.md`) at Stage 0 when the target is a URL. The spine owns the arc, evidence
model, triage, and report; this module owns the consent-gate choice, preconditions,
tool detection, and the probe taxonomy.

## Consent gate

**Gate A — Remote-Target Attestation** (defined in the spine). Web and API both
target a deployed instance someone owns → environment attestation, production
refused.

## Preconditions

- Target URL reachable.
- **Browser MCP** (Claude in Chrome / Preview) available per-category — required for some active categories (see table). At Stage 0, if a browser-dependent category is opted in without browser MCP: *skip · run smell-only · stop*.
- External scanners detected: `zap-baseline.py` / ZAP API · Nuclei · sqlmap · curl. Offer only what's installed.

## Target sub-type

- **Web** (has a browser UI): all categories apply, including the browser-only ones.
- **API** (headless — JSON / GraphQL / gRPC): browser-only categories auto-skip; the API-specific categories below apply. Detect via the root response (HTML vs JSON) or ask.

## Stage 1 — Reconnaissance (`recon` tier)

| Probe | What it checks | CWE |
|---|---|---|
| HTTP security headers | CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy | CWE-693, CWE-1021, CWE-319 |
| TLS basics | HTTPS enforcement, weak ciphers, mixed content | CWE-319, CWE-327 |
| Cookie attributes | `Secure`, `HttpOnly`, `SameSite` on session cookies | CWE-614, CWE-1004, CWE-1275 |
| Disclosure | stack traces, version banners, debug info, `console.log` leaks | CWE-209, CWE-200 |
| Surface exposure | `robots.txt`, `sitemap.xml`, `.well-known/`, common admin paths | CWE-538 |
| ZAP baseline / Nuclei (if available) | `passive`-state findings, normalized into the finding shape | (per alert) |

Findings here are state `passive`.

## Stage 2 — Smell-test (one opt-in)

| Probe | Catches | State | CWE |
|---|---|---|---|
| Reflected input echo | XSS / injection smell | suspected | CWE-79, CWE-74 |
| Open redirect | URL param reaches another origin | suspected | CWE-601 |
| IDOR smell | swap id; observe response delta | suspected | CWE-639 |
| CORS misconfig | loose `Access-Control-Allow-*` | suspected | CWE-942 |
| Auth required | protected route reachable unauthenticated | confirmed if direct, else suspected | CWE-306 |
| Mass assignment | extra fields take effect | suspected | CWE-915 |

## Stage 2 — Active exploit (per-category opt-in)

Non-destructive PoC. Browser-MCP dependency resolved per the spine's degrade rule (Stage 0.6).

| Category | PoC technique | State | Browser MCP? | CWE |
|---|---|---|---|---|
| XSS (reflected / stored) | DOM-mutation (`document.title='XSS-PoC'`) then revert | confirmed (browser) · suspected (without) | required for confirmed | CWE-79 |
| DOM XSS | drive JS sources in browser; observe sink execution | confirmed | **required** | CWE-79 |
| CSP enforcement | inject a payload the CSP should block; observe blocking | confirmed | **required** | CWE-693 |
| Clickjacking | load page in an `<iframe>`; observe rendering vs header | confirmed | **required** | CWE-1021 |
| SQL injection | time-based / error-based; prefer `sqlmap --risk=1 --level=1` | confirmed | no | CWE-89 |
| Command injection | `; sleep 5` timing PoC | confirmed | no | CWE-78 |
| Path traversal | read `/etc/passwd` or equivalent | confirmed | no | CWE-22 |
| SSRF | probe `localhost:80`, cloud metadata endpoint | confirmed | no | CWE-918 |
| Template injection | `{{7*7}}` math eval | confirmed | no | CWE-1336 |
| Auth bypass | token swap, role escalation via parameter | confirmed | optional | CWE-287 |
| CSRF | cross-origin form/fetch with real session state | confirmed (browser) · suspected (without) | required for confirmed | CWE-352 |

### API-specific (when the target is headless)

| Category | PoC technique | State | CWE |
|---|---|---|---|
| BOLA (object-level authz) | access another object's id with a low-privilege token | confirmed on cross-object data | CWE-639 |
| BFLA (function-level authz) | call an admin function with a non-admin token | confirmed on privileged action | CWE-285 |
| Mass assignment | POST extra privileged fields | confirmed if persisted | CWE-915 |
| Unrestricted resource use | many requests; observe whether rate limiting kicks in | suspected (**do not DoS** — cap requests) | CWE-770 |

## Honest limitations (HTTP)

- Browser-MCP-required categories degrade to smell-only or skip without it (per Stage 0.6).
- API auth probes need at least one valid token — and ideally two roles for BOLA/BFLA. Ask if absent.
- Rate-limit probing must **not** become a DoS — cap requests; report "no limit observed," never hammer the target.
