# Symptom Module — Stuck Consumer

Failure-mode content for the **stuck consumer / no progress** class. Loaded by the
`ce-debug` plan-free spine (`SKILL.md`) at Stage 0. The spine owns the arc, the
evidence model, the grading, and the report; this module owns the class-specific
intake questions, the mechanism-map checklist, the failure-mode bank, and the
signal triage.

**Technology-agnostic by design.** "Consumer" here means anything that should be
draining work and isn't: a message-queue or event-stream consumer, a job/worker
framework, a scheduled task, a poller, a file watcher. Named technologies below
are *examples* of where a mechanism shows up, never preconditions.

## Applies when

- Messages / jobs / events accumulate while the consumer process appears healthy.
- Throughput is zero (or near-zero) but the process is "running" — no crash, no alert.
- Consumer lag or queue depth grows monotonically; the last-processed timestamp is stale.
- A scheduled task stopped firing, or fires without effect.
- Some work processes and some never does (partial stall).
- It worked until time T and nothing obviously crashed.

## Stage 0 — class-specific intake (fold into the spine's grouped round)

- What technology moves the work — broker, job framework, scheduler, poll loop?
  Which queue / topic / subscription / consumer group / job type, exactly?
- One queue stalled or all? One consumer instance or all instances?
- Does **restarting the consumer fix it** (even temporarily)? *(The single most
  classifying answer in this module — see the triage table.)*
- Is there a dead-letter / failed-job destination — and is it growing, empty, or absent?
- Can broker-side state be read (queue depth, in-flight/un-acked counts, the
  broker's consumer list, lock/lease tables, consumer-group offsets)? By whom?
- What do the consumer's own logs show at and after the onset — errors, silence,
  or normal chatter?

## Signal → family triage

Use the intake answers to order the bank walk — this prioritizes; it never skips
a family whose mechanism exists in the code.

| Observed signal | Look first at |
|---|---|
| Restart fixes it, no code change involved | C3 (in-process variant), C5, D1, D2, E4 (in-memory variant), F1 — plus any thread-stall mode (B2, C1, C4) |
| One queue / partition / key stalls; siblings flow | A2, E1, E2 — ordering scope, wrong source, filter |
| Zero throughput but the process logs normally | B1, B2, E1, E3 — swallowed failures, dead loop, or consuming the wrong place |
| Error log repeats one message / payload | A1, A3 — poison head or lease-overrun redelivery |
| Messages vanish but *this* consumer did nothing | E3 first (competing consumer), then E2, E5 |
| Work is skipped or never selected, with no errors | E6 — progress marker stuck or wrong |
| Scheduled / timer work stops firing; no tick lines | F2, E4, C3 (a scheduler lock) |
| Stall onset correlates with load / volume growth | C2, C5, F1, D3 |
| Stall onset correlates with a deploy or config change | E1, E2 — plus Stage 1's what-changed git evidence |
| Total silence after an error burst | B2, D1, D2, E4 |
| Gradual slowdown, then stop | F3, C2, D3 |

## Stage 1 — mechanism-map checklist

Map these for the suspect consumer (each node cited `file:line` / config key):

- **Receive path** — how work arrives (push subscription, poll loop, timer,
  watcher) and the loop's **supervision**: what observes it, what restarts it.
- **Dispatch** — concurrency model (single-threaded, pool, per-partition) and any
  ordering scopes (sessions, partitions, FIFO groups, job serialization keys).
- **Completion path** — ack / complete / commit / checkpoint: where it happens, on
  which thread, and on which error paths it is *skipped*.
- **Failure path** — every catch on the handler route; the retry policy (attempt
  counter? cap? backoff cap?); the dead-letter / failed-job path.
- **Locks & leases** — in-process locks/semaphores, distributed locks (DB
  advisory, Redis, blob lease), scheduler locks; their TTLs and whether release is
  exception-safe.
- **Connection & credentials** — where created, refresh/reconnect policy, receive
  timeouts, keepalive.
- **Configuration as loaded** — source names, filters/selectors/bindings,
  prefetch / max-in-flight, concurrency limits, per-environment overrides.
- **Observability** — which log lines would fire on each path above. *(This powers
  the discrimination plan: a path with no log line needs a different discriminator.)*

## The failure-mode bank

For each entry: the mechanism, the **static signatures** to look for in code and
config, and the **runtime discriminator** that would settle it. Include an entry
iff its mechanism precondition exists in the mapped code (spine Stage 2).

### Family A — Head-of-line blocking

| Mode | Mechanism | Static signatures | Runtime discriminator |
|---|---|---|---|
| **A1 — Poison message, retry-forever** | one failing message is redelivered without a max-delivery / dead-letter path and blocks the head for ordered or single-threaded consumption | no DLQ / max-delivery config; catch → nack/abandon/requeue with no attempt counter; ordered or concurrency-1 consumption | the same message id at the head across retries; delivery count climbing; DLQ empty while the error log repeats one payload |
| **A2 — Ordering-scope starvation** | an ordering scope (partition, session, FIFO group, serialization key) pins everything behind one bad key; other keys flow | session-/partition-/group-ordered consumer configuration | lag concentrated on one partition / session / key while others stay current |
| **A3 — Lease / visibility-timeout overrun** | processing time exceeds the delivery lease (visibility timeout, lock duration, ack deadline) and no renewal/heartbeat runs; completion then fails — the lease is gone — and the same work is redelivered forever, often to another instance, multiplying duplicates while net progress stays ~zero | lease / visibility / ack-deadline config vs the handler's worst-case duration; no lock-renewal or heartbeat; completion errors ("lock lost", "receipt expired") swallowed | handler logs *success* yet delivery count climbs; lease-expired / lock-lost errors at completion; duplicate processing observed downstream |

### Family B — Silent failure

| Mode | Mechanism | Static signatures | Runtime discriminator |
|---|---|---|---|
| **B1 — Swallowed handler exception** | a catch-all continues without completing/acking or surfacing — work is neither processed nor visibly failed | empty catch; log-and-continue at debug level; missing rethrow; unobserved async failure (un-awaited task/promise, `async void`, missing `.catch`, discarded error returns, errors sent to a channel nobody reads); a blanket framework-level recovery wrapper swallowing handler panics/exceptions | processed count flat while receive count grows; **no error logs despite stalled output — the silence is the signal** |
| **B2 — Dead dispatch loop, live process** | the receive/poll loop itself exits or dies (exception outside the per-message try, cancelled token, unsupervised background thread death) while the host process stays up and "healthy" | `while(true)` without an outer try/restart; the loop's task/thread not supervised or awaited; liveness probe not tied to loop progress | the loop's own log lines stop at time T while other components keep logging; a thread dump shows no consumer thread |

### Family C — Concurrency

| Mode | Mechanism | Static signatures | Runtime discriminator |
|---|---|---|---|
| **C1 — Sync-over-async / blocked event loop** | the handler blocks the very thread or context its completion needs (blocking waits on async results under a synchronization context; synchronous I/O on an event loop) | `.Result` / `.Wait()` / `get()` on futures in the handler path; sync I/O inside event-loop callbacks | a stack/thread dump showing the handler parked on a task/future wait |
| **C2 — Pool exhaustion** | handlers hold all DB/HTTP/thread-pool slots — often via a missing release/dispose leak — until none remain; consumption stalls behind pool waits | acquire without `finally`/`using`/`with`; pool max vs consumer concurrency mismatch | pool metrics pinned at max with queued waiters; stall onset correlates with cumulative throughput |
| **C3 — Unreleased lock / lease** | an exception path skips release, or a distributed lock (DB advisory, Redis, blob lease, scheduler lock) is held by a dead holder with no TTL | acquire/release not exception-safe; lock TTL absent or huge; singleton-host scheduling | live lock/lease state names a holder that is dead or is not this node; restarting the stuck consumer does *not* clear it (separating distributed C3 from D1/F1) — release needs the holder's restart, TTL expiry, or manual removal; the *in-process* variant clears on restarting the same node |
| **C4 — Internal deadlock** | two locks acquired in opposite orders, or a bounded internal queue/channel the consumer both fills and drains | nested lock acquisition across components; producer-and-consumer on the same bounded channel | a thread dump showing the cycle |
| **C5 — Handler hung on a no-timeout downstream call** | an outbound call in the handler path (DB, HTTP, cache, file share) has no connect/read timeout — or an infinite library default — and the downstream stalls or the connection goes half-open; the handler parks forever, pinning its in-flight item, and once every worker hits it, consumption stops with no error | outbound clients constructed without explicit timeouts; libraries whose default timeout is infinite; no overall handler deadline or watchdog | a thread/stack dump showing handlers parked in socket reads to the same downstream; that dependency's own health around the onset |

### Family D — Connection & credential lifecycle

| Mode | Mechanism | Static signatures | Runtime discriminator |
|---|---|---|---|
| **D1 — Dead connection, no reconnect** | the transport dropped; the client lacks (or has a broken) reconnect/keepalive path; the receive call waits forever on a dead socket | subscription created once at startup; no reconnect handler or policy; no receive timeout | last network activity timestamp; "restart fixes it" with no code or data change |
| **D2 — Credential expiry mid-run** | a token / cert / signed key is acquired once and never refreshed; the client retries auth failures forever, often silently | credential fetched only at startup; retry-forever on 401/403-class errors | auth errors in logs; credential expiry date vs stall onset |
| **D3 — Throttle / backoff runaway** | server-side throttling drives an uncapped exponential backoff into hours, or an enormous server retry-after is honored verbatim | backoff arithmetic without a max-delay cap; infinite retry budget | throttle responses (429 / busy signals) in logs; monotonically growing inter-attempt gaps |

### Family E — Wrong place / wrong state

| Mode | Mechanism | Static signatures | Runtime discriminator |
|---|---|---|---|
| **E1 — Source misconfiguration** | an environment-drifted queue / topic / subscription / group name — the consumer is healthy on the wrong source | per-environment config for source names; a recent config change in git | broker counters: messages arrive on the queue, deliveries to *this* consumer are zero |
| **E2 — Filter excludes everything** | a subscription rule, message selector, routing binding, or client-side predicate rejects all current messages (often after a producer-side schema / header change) | filter / selector / binding expressions; recent producer changes in git | arriving messages' attributes vs the filter; filtered-out counters where the broker keeps them |
| **E3 — Competing consumer / rebalance churn** | another consumer (or another *environment*) drains the queue; or, on group-protocol brokers, the group rebalances continuously — e.g. a slow handler violating the poll-interval budget — so no member consumes steadily (on lock/lease-delivery brokers the same overrun presents as **A3** instead) | shared group / queue names across environments; handler latency vs the max-poll-interval budget | the broker's consumer list; rebalance events in logs; messages disappearing while this consumer logs nothing |
| **E4 — Paused state never lifted** | a kill switch, pause flag, or circuit breaker stuck open — with a broken half-open recovery — outlives the incident that tripped it; or in-memory flow control never resumes (a `pause()` whose `resume()` is skipped on an error path; reactive demand/credit never re-requested after a failure, leaving the subscription at demand zero) | breaker config without half-open recovery; persisted pause/disable flags; pause/resume not exception-symmetric; demand re-request missing from failure paths | the live flag / breaker state; the client's paused-partitions / outstanding-demand state (the in-memory variant is restart-fixable) |
| **E5 — Broker discards work by policy** | TTL / max-length / retention removes (or dead-letters) messages before this consumer receives them; or stream retention shorter than the consumer's lag or downtime, followed by an auto-reset-to-latest jump over the gap | TTL / max-length / retention configuration; auto-reset-to-latest on a missing position; consumer downtime or lag windows exceeding retention | the broker's expired/dropped counters; DLQ growth with an expiry reason; a position jump in the consumer's offsets |
| **E6 — Progress marker stuck or wrong** | the consumer derives what-to-process-next from a persisted marker (offset, checkpoint, cursor, last-run timestamp) that is wrong — committed before processing completes, never advancing because its write fails silently, or compared against a skewed clock — so it permanently skips or never selects work | marker persisted before / independently of completion; marker-write errors swallowed; `> last_run` timestamp comparisons (clock-skew-sensitive) | the live marker value vs the actual newest work — frozen behind it or jumped ahead of it; the marker not moving across runs |

### Family F — Capacity & scheduling

| Mode | Mechanism | Static signatures | Runtime discriminator |
|---|---|---|---|
| **F1 — In-flight cap saturated** | all prefetched / in-flight work is stuck un-acked (each item held by a B/C mode) so the broker delivers nothing new; the consumer *looks* idle | prefetch / max-in-flight config combined with any blocking mode above | un-acked / in-flight count pinned exactly at the cap |
| **F2 — Schedule never fires** | a wrong cron expression or timezone, a missed-fire policy that discards, or a poll timer cancelled by its first exception and never rescheduled | cron strings + TZ handling; timer rescheduling not exception-safe; missed-fire policy | the scheduler's next-fire-time state; absence of "tick" log lines |
| **F3 — Host/runtime exhaustion presenting as stuck** | GC death spiral, file-descriptor limit, disk full, memory pressure — no crash, no progress | (weak, static) unbounded in-memory buffering or batching | host metrics: time-in-GC, fd count, disk; largely environment evidence — route to ops via the discrimination plan |

## Honest limitations (stuck-consumer)

- **The decisive discriminators live broker-side** — queue depths, un-acked
  counts, consumer lists, lock tables, offsets. This tool cannot read them; the
  discrimination plan must tell the human *exactly* what to fetch and from where.
- **"Restart fixes it" is testimony, not proof.** It is the strongest single
  family classifier in the triage table, but it is human-provided and confirms no
  specific hypothesis alone.
- **A producer-side stall looks identical from this repo.** If nothing is being
  *sent*, the consumer is innocent. E1/E2's broker-counter discriminator (arriving
  vs delivered) doubles as the producer-vs-consumer discriminator — when
  total-silence signals fire, run it first. And work that *was* sent under a
  transaction that never committed also stalls transactionally-isolated consumers
  and outbox relays while both ends look healthy — have the human check the
  broker's open/hung-transaction state and the outbox table's unpublished rows
  alongside the arriving-vs-delivered counters.
