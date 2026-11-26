from topology.ports import BusinessError, require_port


def resolve_input_binding(layout, requested_input):
    port = require_port(layout.ports, requested_input)
    if port.name != layout.start:
        raise BusinessError('INPUT_MISMATCH', 'Input must match the published speaking port')
    return port.name
