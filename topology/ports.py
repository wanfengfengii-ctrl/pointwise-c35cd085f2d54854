from dataclasses import dataclass


class BusinessError(ValueError):
    def __init__(self, code, detail, http_status=422):
        super().__init__(detail)
        self.code = code
        self.http_status = http_status


def require_name(value, field):
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise BusinessError('INVALID_NAME', f'{field} must be a nonempty, trimmed string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise BusinessError('INVALID_NAME', f'{field} must be valid Unicode') from error
    return value


@dataclass(frozen=True)
class Port:
    name: str


def validate_ports(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise BusinessError('INVALID_PORTS', 'ports must be a nonempty array')
    names = [require_name(value, 'port') for value in values]
    if len(names) != len(set(names)):
        raise BusinessError('DUPLICATE_PORT', 'port names must be unique')
    return tuple(Port(name) for name in sorted(names))


def require_port(ports, value):
    name = require_name(value, 'port')
    for port in ports:
        if port.name == name:
            return port
    raise BusinessError('UNKNOWN_PORT', f'Unknown port {name!r}')
