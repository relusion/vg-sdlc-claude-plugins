"""Tiny entry point for the snippet vault — the integration-verify smoke target."""

from snippets import Store, list_snippets


def main() -> None:
    store = Store()
    print(f"snippet-vault: {len(list_snippets(store))} snippet(s)")


if __name__ == "__main__":
    main()
