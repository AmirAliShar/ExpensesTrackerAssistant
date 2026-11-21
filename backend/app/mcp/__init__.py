__all__ = [
    "mcp",
    "InsertItem",
    "get_expenses_record",
    "record_transaction",
    "save_user_memory"
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from app.mcp import server

    return getattr(server, name)
