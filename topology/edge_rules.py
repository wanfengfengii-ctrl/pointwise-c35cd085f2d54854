from dataclasses import dataclass

from topology.ports import BusinessError, require_name


Edge = tuple[str, str]
EdgeSet = frozenset[Edge]


@dataclass(frozen=True)
class EdgeRule:
    edge: Edge
    owner: str


def canonical_edges(values):
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise BusinessError('INVALID_EDGES', 'edges must be an array of port pairs')
    edges = set()
    for entry in values:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise BusinessError('INVALID_EDGES', 'each edge must have two port names')
        source, destination = entry
        edges.add((require_name(source, 'source'), require_name(destination, 'destination')))
    return frozenset(edges)


def validate_edge_set(values, rules):
    edges = canonical_edges(values)
    unallowed = edges - {rule.edge for rule in rules}
    if unallowed:
        raise BusinessError('UNALLOWED_EDGE', f'Edge {min(unallowed)!r} is outside the layout')
    return edges


def owned_edge_delta(rules, owner, before, after):
    removed = before - after
    added = after - before
    allowed = {rule.edge for rule in rules if rule.owner == owner}
    if (removed | added) - allowed:
        raise BusinessError('WRONG_EDGE_OWNER', f'Step changes edges outside endpoint {owner!r}')
    return removed, added
