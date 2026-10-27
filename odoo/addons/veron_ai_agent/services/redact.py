"""Keys, tokens and passwords are taken out of anything written to a log, an audit event or a run."""

import json
import re

PATTERNS = [
	re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
	re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
	re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
	re.compile(r"(?i)((?:api[_-]?key|token|secret|password|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{4,}"),
]
SECRET_KEYS = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|credential)")


def text(value, limit=4000):
	value = str(value or "")
	for pattern in PATTERNS:
		value = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[hidden]", value)
	return value[:limit]


def data(value, depth=0):
	"""A copy of a JSON-like value with secret keys hidden and long strings cut"""
	if depth > 8:
		return "…"
	if isinstance(value, dict):
		return {k: "[hidden]" if SECRET_KEYS.search(str(k)) else data(v, depth + 1) for k, v in value.items()}
	if isinstance(value, (list, tuple)):
		return [data(v, depth + 1) for v in value[:200]]
	if isinstance(value, str):
		return text(value, 2000)
	return value


def dumps(value, limit=20000):
	return json.dumps(data(value), ensure_ascii=False, default=str)[:limit]
