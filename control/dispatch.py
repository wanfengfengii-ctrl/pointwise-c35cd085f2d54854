from control.orders import admit_order, finish_order, get_order, matching_order, update_order_progress
from control.preview import open_layout, preview_change
from control.route_search import RouteStep, find_route_plan
from endpoint.commands import WiringCommand, accept_command, get_command
from endpoint.local_wiring import apply_local_command, read_actual_wiring
from endpoint.outcomes import read_commit_outcome
from endpoint.store import write_transaction
from topology.edge_rules import canonical_edges
from topology.ports import BusinessError, require_name


def deliver_local(db, command):
    return apply_local_command(db, command.session, command.operation, command.step)


def submit_change(db, session, operation, target, deliver=deliver_local):
    session = require_name(session, 'session')
    operation = require_name(operation, 'operation')
    target = canonical_edges(target)
    with write_transaction(db):
        if matching_order(db, session, operation, target, None) is None:
            preview_change(db, session, target)
            admit_order(db, session, operation, target)
    return resume_order(db, session, operation, deliver)


def _prepare_next(db, session, operation):
    with write_transaction(db):
        order = get_order(db, session, operation)
        if order is None:
            raise BusinessError('UNKNOWN_OPERATION', 'No such operation for this session', 404)
        if order.status != 'pending':
            return None
        if order.replaces is not None and get_order(db, session, order.replaces).status == 'suspended':
            return None

        actual = read_actual_wiring(db, session)
        if order.waiting_step is not None:
            step = order.waiting_step
            outcome = read_commit_outcome(db, session, operation, step)
            if outcome is None:
                return get_command(db, session, operation, step)
            update_order_progress(db, order, step, None)
            order = get_order(db, session, operation)

        layout = open_layout(db, session)
        plan = find_route_plan(layout, actual, order.target)
        if plan is None:
            finish_order(db, order, 'rejected', actual, 'UNREACHABLE_TARGET')
            return None
        if not plan.steps:
            finish_order(db, order, 'completed', actual)
            return None

        next_step = plan.steps[0]
        additions = order.target - actual
        if order.progress == 0 and len(additions) == 1:
            edge, = additions
            owner = next(rule.owner for rule in layout.rules if rule.edge == edge)
            next_step = RouteStep(owner, frozenset(), additions)
        command = WiringCommand(session, operation, order.progress + 1, next_step.owner,
                                actual, next_step.removed, next_step.added)
        accepted = accept_command(db, layout, command)
        update_order_progress(db, order, order.progress, accepted.step)
        return accepted


def advance_order(db, session, operation, deliver=deliver_local):
    while True:
        command = _prepare_next(db, session, operation)
        if command is None:
            return get_order(db, session, operation)
        outcome = deliver(db, command)
        if outcome is None:
            return get_order(db, session, operation)
        if outcome.state != 'applied':
            with write_transaction(db):
                order = get_order(db, session, operation)
                if (order.status == 'pending' and order.waiting_step == command.step
                        and read_commit_outcome(db, session, operation, command.step) is None):
                    finish_order(db, order, 'rejected', read_actual_wiring(db, session),
                                 outcome.reason or 'STEP_REJECTED')
            return get_order(db, session, operation)


def resume_order(db, session, operation, deliver=deliver_local):
    order = get_order(db, session, operation)
    if order is None:
        raise BusinessError('UNKNOWN_OPERATION', 'No such operation for this session', 404)
    if order.status != 'pending':
        return order
    if order.replaces is not None:
        from control.replacement import advance_replacement
        return advance_replacement(db, session, operation, deliver)
    return advance_order(db, session, operation, deliver)
