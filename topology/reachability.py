from collections import deque
from dataclasses import dataclass

from topology.ports import BusinessError


@dataclass(frozen=True)
class PathAssessment:
    state: str
    path: tuple[str, ...] = ()

    def require_unique(self):
        errors = {
            'feedback': ('FEEDBACK_LOOP', 'The layout has a directed feedback loop'),
            'silent': ('NO_LIVE_PATH', 'No route reaches the listener'),
            'duplicate': ('DUPLICATE_LIVE_PATH', 'More than one route reaches the listener'),
        }
        if self.state != 'unique':
            raise BusinessError(*errors[self.state])
        return self.path


def _graph_order(layout, edges):
    outgoing = {port.name: [] for port in layout.ports}
    incoming = dict.fromkeys(outgoing, 0)
    for source, destination in sorted(edges):
        outgoing[source].append(destination)
        incoming[destination] += 1
    ready = deque(sorted(port for port, count in incoming.items() if not count))
    order = []
    while ready:
        port = ready.popleft()
        order.append(port)
        for destination in outgoing[port]:
            incoming[destination] -= 1
            if incoming[destination] == 0:
                ready.append(destination)
    return outgoing, order


def detect_cycle(layout, edges):
    outgoing, order = _graph_order(layout, edges)
    return len(order) != len(outgoing)


def assess_paths(layout, edges):
    outgoing, order = _graph_order(layout, edges)
    if len(order) != len(outgoing):
        return PathAssessment('feedback')
    counts = {}
    for port in reversed(order):
        if port == layout.listener:
            counts[port] = 1
        else:
            counts[port] = min(2, sum(counts[child] for child in outgoing[port]))
    if counts[layout.start] == 0:
        return PathAssessment('silent')
    if counts[layout.start] > 1:
        return PathAssessment('duplicate')
    path = [layout.start]
    while path[-1] != layout.listener:
        path.append(next(child for child in outgoing[path[-1]] if counts[child]))
    return PathAssessment('unique', tuple(path))
