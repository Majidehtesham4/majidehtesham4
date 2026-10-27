"""The registry of agent tools. A tool is a small, fixed piece of code: what it may do, on which models,
with which arguments, at which authority level and risk. A language model only names a tool and gives
arguments; the arguments are validated against the tool's schema, the agent's grant and the person's
own access rights are checked, and only then does the tool's own code run - never code or queries the
model wrote. Modules add tools with the `tool` decorator."""

from dataclasses import dataclass, field

from . import schema as schemas

# The authority each kind of action needs
LEVELS = {"read": 1, "suggest": 2, "draft": 3, "execute": 4}
LEVEL_NAMES = [
	("1", "1. Read, Analyze and Report"),
	("2", "2. Suggest Actions, Change Nothing"),
	("3", "3. Make Drafts and Ask for Approval"),
	("4", "4. Act Automatically Within Set Limits"),
]
RISKS = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
# Actions that always need a person's approval, unless a manager sets an explicit, limited rule for them
SENSITIVE = [
	("post", "Posting an Entry or Document"),
	("payment", "Payment"),
	("bank", "Changing Bank Details"),
	("delete", "Deleting Data"),
	("close_period", "Closing a Period"),
	("legal_report", "Sending a Legal Report"),
	("publish", "Publishing Public Content"),
	("external_contact", "Contacting Someone Outside"),
]
CATEGORIES = [
	("read", "Read Data"),
	("analyze", "Analysis"),
	("report", "Report"),
	("suggest", "Suggestion"),
	("draft", "Draft"),
	("execute", "Action"),
	("notify", "Notification"),
	("external", "Outside Service"),
	("human", "Asking a Person"),
	("coordinate", "Coordination"),
]
TOOLS = {}


class ToolDenied(Exception):
	"""The tool may not do this; the message says why, in words the person and the model understand"""


class ToolNeedsInfo(Exception):
	"""Data the tool needs is missing (a rate, a rule, a document): the run stops and asks a person"""


@dataclass
class Plan:
	"""What a tool is about to do, checked before it does it"""

	summary: str
	amount: float = 0.0
	company_ids: list = field(default_factory=list)
	model: str = ""
	res_ids: list = field(default_factory=list)
	data: dict = field(default_factory=dict)


class Tool:
	code = ""
	name = ""
	description = ""
	category = "read"
	action = "read"
	risk = "low"
	sensitive = ""
	models = ()
	supervisor_only = False
	schema = schemas.strict_object({})
	# The module that brings the tool, shown when a role needs it and it is missing
	module = "veron_ai_agent"

	@property
	def level(self):
		return LEVELS[self.action]

	def available(self, env):
		return all(model in env for model in self.models)

	def validate(self, args):
		return schemas.validate(args or {}, self.schema)

	def plan(self, ctx, args):
		"""The checked description of the action; it changes nothing"""
		return Plan(summary=self.name)

	def execute(self, ctx, args, plan):
		"""Does the action with the environment of the person it runs for; returns a JSON-like dict"""
		raise NotImplementedError

	def definition(self):
		"""What the language model sees of the tool"""
		return {"name": self.code, "description": f"{self.name}. {self.description}", "input_schema": self.schema}


def tool(cls):
	assert cls.code and cls.code not in TOOLS, cls.code
	TOOLS[cls.code] = cls()
	return cls


def get(code):
	return TOOLS.get(code)
