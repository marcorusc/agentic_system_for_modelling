"""Technical lifecycle only; never interprets scientific handoff statuses."""
from .models import ExecutionState as State

TERMINAL = frozenset({State.SUCCEEDED, State.FAILED, State.CANCELLED})
TRANSITIONS = {
    State.QUEUED: {State.PREFLIGHTING, State.FAILED, State.CANCELLED},
    # A backendless literature request validates a blocked handoff without a child.
    State.PREFLIGHTING: {State.RUNNING, State.VALIDATING, State.FAILED, State.CANCELLED},
    State.RUNNING: {State.VALIDATING, State.FAILED, State.CANCELLED},
    State.VALIDATING: {State.RECORDING, State.FAILED, State.CANCELLED},
    State.RECORDING: {State.SUCCEEDED, State.FAILED, State.CANCELLED},
    **{state: set() for state in TERMINAL},
}


def validate_transition(previous: str, following: str) -> None:
    if State(following) not in TRANSITIONS[State(previous)]:
        raise ValueError(f"illegal execution transition: {previous} -> {following}")
