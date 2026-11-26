from dataclasses import dataclass

from topology.edge_rules import EdgeRule, EdgeSet, validate_edge_set
from topology.ports import BusinessError, Port, require_name, require_port, validate_ports


@dataclass(frozen=True)
class Layout:
    ports: tuple[Port, ...]
    start: str
    listener: str
    rules: tuple[EdgeRule, ...]
    initial: EdgeSet

    def as_definition(self):
        return {
            'ports': [port.name for port in self.ports],
            'start': self.start,
            'listener': self.listener,
            'allowed': [[*rule.edge, rule.owner] for rule in self.rules],
            'initial': sorted(self.initial),
        }


def build_layout(definition):
    if not isinstance(definition, dict):
        raise BusinessError('INVALID_LAYOUT', 'layout must be an object')
    ports = validate_ports(definition.get('ports'))
    start = require_port(ports, definition.get('start')).name
    listener = require_port(ports, definition.get('listener')).name
    candidates = definition.get('allowed')
    if not isinstance(candidates, list):
        raise BusinessError('INVALID_RULES', 'allowed must be an array of edge and owner triples')
    ownership = {}
    for candidate in candidates:
        if not isinstance(candidate, list) or len(candidate) != 3:
            raise BusinessError('INVALID_RULES', 'each rule needs source, destination and owner')
        source, destination, owner = candidate
        edge = (require_port(ports, source).name, require_port(ports, destination).name)
        owner = require_name(owner, 'endpoint owner')
        if edge in ownership:
            raise BusinessError('DUPLICATE_EDGE_RULE', f'Edge {edge!r} has multiple declarations')
        ownership[edge] = owner
    rules = tuple(EdgeRule(edge, owner) for edge, owner in sorted(ownership.items()))
    initial = validate_edge_set(definition.get('initial'), rules)
    return Layout(ports, start, listener, rules, initial)
