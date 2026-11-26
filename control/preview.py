from dataclasses import dataclass

from control.route_search import RoutePlan, find_route_plan
from endpoint.local_wiring import read_actual_wiring
from session.status import require_open
from topology.edge_rules import validate_edge_set
from topology.ports import BusinessError
from topology.publication import load_publication
from topology.reachability import assess_paths


@dataclass(frozen=True)
class PreviewResult:
    path: tuple[str, ...]
    plan: RoutePlan

    def as_response(self):
        return {'status': 'reachable', 'path': self.path,
                'steps': [step.as_summary() for step in self.plan.steps]}


def open_layout(db, session):
    status = require_open(db, session)
    return load_publication(db, session, status.reference).layout


def preview_change(db, session, target):
    layout = open_layout(db, session)
    target = validate_edge_set(target, layout.rules)
    path = assess_paths(layout, target).require_unique()
    actual = read_actual_wiring(db, session)
    plan = find_route_plan(layout, actual, target)
    if plan is None:
        raise BusinessError('UNREACHABLE_TARGET', 'No legal sequence of endpoint commits')
    return PreviewResult(path, plan)
