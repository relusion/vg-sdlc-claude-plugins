INVITATIONS = {}


def create_invitation(team_id: str, email: str, role: str) -> dict:
    invitation_id = f"inv_{len(INVITATIONS) + 1}"
    invitation = {
        "id": invitation_id,
        "team_id": team_id,
        "email": email,
        "role": role,
        "status": "pending",
    }
    INVITATIONS[invitation_id] = invitation
    return invitation

