from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import combinations

from topology.edge_rules import EdgeSet, owned_edge_delta
from topology.reachability import assess_paths


@dataclass(frozen=True)
class RouteStep:
    owner: str
    removed: EdgeSet
    added: EdgeSet

    def as_summary(self):
        return {'owner': self.owner, 'removed': sorted(self.removed), 'added': sorted(self.added)}


@dataclass(frozen=True)
class RoutePlan:
    steps: tuple[RouteStep, ...]


def _endpoint_choices(rules):
    groups = defaultdict(set)
    for rule in rules:
        groups[rule.owner].add(rule.edge)
    for owner, edges in sorted(groups.items()):
        ordered = sorted(edges)
        choices = [frozenset(subset) for size in range(len(ordered) + 1)
                   for subset in combinations(ordered, size)]
        yield owner, frozenset(edges), choices


def _route_plan(rules, parents, goal):
    steps = []
    while parents[goal] is not None:
        previous, owner = parents[goal]
        removed, added = owned_edge_delta(rules, owner, previous, goal)
        steps.append(RouteStep(owner, removed, added))
        goal = previous
    return RoutePlan(tuple(reversed(steps)))


def find_route_plan(layout, start, goal):
    assess_paths(layout, goal).require_unique()
    assess_paths(layout, start).require_unique()
    if start == goal:
        return RoutePlan(())
    endpoint_choices = tuple(_endpoint_choices(layout.rules))
    parents = {start: None}
    invalid = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for owner, owned_edges, choices in endpoint_choices:
            rest = current - owned_edges
            for choice in choices:
                candidate = rest | choice
                if candidate in parents or candidate in invalid:
                    continue
                if assess_paths(layout, candidate).state != 'unique':
                    invalid.add(candidate)
                    continue
                parents[candidate] = (current, owner)
                if candidate == goal:
                    return _route_plan(layout.rules, parents, goal)
                queue.append(candidate)
    return None
