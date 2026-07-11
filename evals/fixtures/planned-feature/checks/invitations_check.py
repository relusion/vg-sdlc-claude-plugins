from src.invitations import create_invitation


def test_create_invitation_records_pending_role():
    invitation = create_invitation("team_1", "new@example.com", "viewer")
    assert invitation["status"] == "pending"
    assert invitation["role"] == "viewer"
