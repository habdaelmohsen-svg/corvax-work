"""Compatibility entry points for the retired external sales worker.

Retained so an old process command cannot restart remote synchronization.
"""


def run_due_syncs() -> None:
    return None


async def scheduler_loop() -> None:
    return None
