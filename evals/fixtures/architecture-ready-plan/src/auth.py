ROLES = {"owner", "admin", "member"}


def authorize(capabilities: set[str], required: str) -> bool:
    return required in capabilities
