STATUS_LABELS = {
    "open": "Open",
    "paid": "Piad",
    "void": "Void",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())

