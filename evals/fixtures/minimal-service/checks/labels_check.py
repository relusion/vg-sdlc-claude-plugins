from labels import status_label


def test_archived_status_label_is_spelled_correctly():
    assert status_label("archived") == "Archived"
