STATUS_LABELS = {
    "active": "Active",
    "archived": "Archvied",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())
