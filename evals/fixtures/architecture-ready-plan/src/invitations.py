def accept_invitation(invitation: dict, memberships: dict) -> dict:
    key = (invitation["team_id"], invitation["user_id"])
    memberships.setdefault(key, {"role": invitation["role"]})
    return memberships[key]
