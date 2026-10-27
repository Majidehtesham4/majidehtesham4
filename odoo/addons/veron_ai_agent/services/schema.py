"""A small validator for the JSON-schema subset the agent tools use. Every argument a language model
gives a tool goes through it: unknown keys, wrong types, values outside an enum or a range, and strings
or lists over their length are refused, so no unchecked value reaches a tool."""


class SchemaError(ValueError):
	pass


TYPES = {
	"string": str,
	"integer": int,
	"number": (int, float),
	"boolean": bool,
	"array": list,
	"object": dict,
}
# Defaults that bound what a model may send even when a schema forgets to
MAX_STRING = 4000
MAX_ITEMS = 200


def _check_type(value, expected, path):
	types = expected if isinstance(expected, list) else [expected]
	for kind in types:
		if kind == "null" and value is None:
			return kind
		python_type = TYPES.get(kind)
		if python_type is None:
			continue
		# A boolean is an int in Python; it is not a number here
		if kind in ("integer", "number") and isinstance(value, bool):
			continue
		if kind == "integer" and isinstance(value, float) and value.is_integer():
			return kind
		if isinstance(value, python_type):
			return kind
	raise SchemaError(f"{path}: expected {' or '.join(types)}")


def validate(value, schema, path="input"):
	"""The value, with integers normalized, or SchemaError"""
	kind = _check_type(value, schema.get("type", "object"), path)
	if kind == "null":
		return None
	if "enum" in schema and value not in schema["enum"]:
		raise SchemaError(f"{path}: must be one of {schema['enum']}")
	if kind == "integer":
		value = int(value)
	if kind in ("integer", "number"):
		if "minimum" in schema and value < schema["minimum"]:
			raise SchemaError(f"{path}: must be at least {schema['minimum']}")
		if "maximum" in schema and value > schema["maximum"]:
			raise SchemaError(f"{path}: must be at most {schema['maximum']}")
	if kind == "string":
		if len(value) > schema.get("maxLength", MAX_STRING):
			raise SchemaError(f"{path}: too long")
		if len(value) < schema.get("minLength", 0):
			raise SchemaError(f"{path}: too short")
	if kind == "array":
		if len(value) > schema.get("maxItems", MAX_ITEMS):
			raise SchemaError(f"{path}: too many items")
		if len(value) < schema.get("minItems", 0):
			raise SchemaError(f"{path}: too few items")
		items = schema.get("items")
		if items:
			value = [validate(item, items, f"{path}[{i}]") for i, item in enumerate(value)]
	if kind == "object":
		properties = schema.get("properties", {})
		unknown = set(value) - set(properties)
		if unknown and not schema.get("additionalProperties", False):
			raise SchemaError(f"{path}: unknown keys {sorted(unknown)}")
		missing = [key for key in schema.get("required", []) if key not in value]
		if missing:
			raise SchemaError(f"{path}: missing {missing}")
		value = {key: validate(val, properties[key], f"{path}.{key}") if key in properties else val
			for key, val in value.items()}
	return value


def strict_object(properties, required=()):
	"""An object schema that refuses unknown keys"""
	return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}
