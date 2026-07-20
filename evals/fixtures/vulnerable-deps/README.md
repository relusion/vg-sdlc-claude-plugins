# vulnerable-deps fixture

A tiny service pinning a dependency version with well-known public OSV
advisories (`urllib3==1.24.1` — e.g. CVE-2019-11324 / OSV `PYSEC-2019-133`),
plus an unpinned range the scanner must list as skipped, for `/core-engineering:ce-probe-deps`
(EVAL-016). The probe must find the vulnerable pin with advisory ids, list the
unpinned entry, and never report "clean" when degraded.
