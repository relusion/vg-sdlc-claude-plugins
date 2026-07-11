"""Tiny HTTP fetcher used by the vulnerable-deps eval fixture."""
import urllib3


def fetch(url: str) -> int:
    http = urllib3.PoolManager()
    return http.request("GET", url).status
