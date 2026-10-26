"""Server-owned, typed run extensions. Never accept raw pytest argv from clients."""
from dataclasses import dataclass
from typing import Callable

from triton_dev.common.contracts import ToolError


@dataclass(frozen=True)
class RunExtension:
    name: str
    title: str
    description: str
    schema: dict
    default: object
    compile: Callable
    version: int = 1


_REGISTRY = {}


def register_extension(extension):
    """Called by trusted server code at startup, not by JSON or HTTP requests."""
    if not isinstance(extension, RunExtension) or extension.name in _REGISTRY:
        raise ValueError('Unique RunExtension required')
    if extension.schema.get('type') not in {'integer', 'boolean', 'string'}:
        raise ValueError('Extension requires a supported scalar schema')
    _REGISTRY[extension.name] = extension


def describe_extensions(allowed=None):
    names = list(_REGISTRY) if allowed is None else allowed
    if not isinstance(names, list) or any(not isinstance(n, str) or n not in _REGISTRY for n in names):
        raise ToolError('INVALID_EXTENSION', 'Unknown server extension allowlist')
    return [{'name': name, 'title': _REGISTRY[name].title,
             'description': _REGISTRY[name].description, 'schema': _REGISTRY[name].schema,
             'default': _REGISTRY[name].default, 'version': _REGISTRY[name].version} for name in names]


def validate_extensions(values=None, allowed=None):
    descriptors = {d['name']: d for d in describe_extensions(allowed)}
    if values is None:
        values = {}
    if not isinstance(values, dict) or any(k not in descriptors for k in values):
        raise ToolError('INVALID_EXTENSION', 'Only registered and enabled extensions are accepted')
    result = {}
    for name, spec in descriptors.items():
        value = values.get(name, spec['default'])
        schema = spec['schema']
        kind = schema['type']
        valid = ((kind == 'integer' and type(value) is int)
                 or (kind == 'boolean' and type(value) is bool)
                 or (kind == 'string' and isinstance(value, str)))
        if (not valid or ('enum' in schema and value not in schema['enum'])
                or (kind == 'integer' and not schema.get('minimum', value) <= value <= schema.get('maximum', value))):
            raise ToolError('INVALID_EXTENSION', f'Invalid value for extension {name}')
        result[name] = value
    return result


def compile_extensions(values, versions=None):
    normalized = validate_extensions(values, list(values))
    argv = []
    for name, value in normalized.items():
        extension = _REGISTRY[name]
        if versions and versions.get(name) != extension.version:
            raise ToolError('EXTENSION_CHANGED', f'Extension {name} changed; create a new run configuration')
        compiled = extension.compile(value)
        if not isinstance(compiled, list) or any(not isinstance(a, str) for a in compiled):
            raise ToolError('INVALID_EXTENSION', f'Invalid server compiler for {name}')
        argv.extend(compiled)
    return argv


register_extension(RunExtension(
    'max_failures', '失败停止阈值', '达到多少项失败后停止；0 表示不中断，xdist 中已在运行的配置可能继续完成。',
    {'type': 'integer', 'minimum': 0, 'maximum': 100}, 0, lambda n: ['--maxfail', str(n)]))
register_extension(RunExtension(
    'durations', '慢用例数量', '在进程日志中输出最慢阶段，0 表示关闭。',
    {'type': 'integer', 'minimum': 0, 'maximum': 100}, 0, lambda n: ['--triton-dev-durations', str(n)]))
register_extension(RunExtension(
    'capture', '输出捕获方式', 'fd 同时捕获原生库输出；sys 捕获 Python stdout/stderr。',
    {'type': 'string', 'enum': ['fd', 'sys']}, 'fd', lambda value: ['--capture', value]))
