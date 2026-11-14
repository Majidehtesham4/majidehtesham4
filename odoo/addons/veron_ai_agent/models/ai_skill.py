"""Skills, as in Odoo's AI app: a skill is instructions and the tools that go with them, given to an agent at
once. The tools a skill brings are granted at the agent's own authority; the limits of each grant stay on the
agent. Three tools are switched on and off by themselves: web search, images, and proposing changes to the
agent's own instructions."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services import registry

# The skills the program comes with: name, icon, tools, instructions
BUILTIN = {
	"records": ("Search and Show Information", "fa-search", "records_search,record_read,records_aggregate,page_overview",
		"Find the records the person asks for in the agent's data, with the filters and the grouping they say (by "
		"day, month or year when they ask), and answer with the numbers and names found. Never guess a figure."),
	"documents": ("Read Files and Documents", "fa-file-text-o", "attachment_read,document_extract,spreadsheet_read",
		"Read the files the person gives (invoices, receipts, cheques, sheets) and give back their fields for the "
		"person to check before anything is made of them."),
	"followup": ("Follow-up and Messages", "fa-bell-o", "activity_create,notify_internal,request_human_input,tasks_followup",
		"Plan activities, tell colleagues inside the company and ask a person when information is missing. Messages "
		"to people outside the company are never sent without an approval."),
	"sales": ("Sales and Customers", "fa-line-chart", "sales_summary,quotes_pending,customer_summary",
		"Report on sales, quotations waiting and the history of a customer; amounts in the company's currency."),
	"purchase": ("Purchases and Suppliers", "fa-shopping-cart", "purchase_summary,purchase_late,purchase_compare,order_receipt_bill_check",
		"Report on purchases, late orders and suppliers' prices, and check orders against receipts and bills."),
	"stock": ("Stock", "fa-cubes", "stock_alerts,stock_transfer_suggest,stock_transfer_draft",
		"Report the products under their minimum and suggest transfers; a transfer is only made as a draft."),
	"hr": ("Employees", "fa-users", "employee_missing_info,attendance_leave_review",
		"Find what is missing in the employees' files and review attendances and leaves."),
	"content": ("Write Content", "fa-pencil", "content_draft",
		"Write drafts of texts (posts, emails, descriptions) in the company's tone; a person publishes them."),
	"knowledge": ("Answer From the Company's Knowledge", "fa-book", "knowledge_sources",
		"Answer from the agent's knowledge sources first, and say which source an answer comes from."),
}
# Their names and descriptions in Persian
FA = {
	"records": ("جستجو و نمایش اطلاعات", "پیدا کردن رکوردها، جمع و گروه‌بندی آن‌ها و نمایش صفحه مناسب"),
	"documents": ("خواندن فایل‌ها و اسناد", "خواندن فاکتور، رسید، چک و فایل اکسل و برگرداندن فیلدهایشان"),
	"followup": ("پیگیری و پیام", "ساخت فعالیت، خبر دادن به همکاران و پرسیدن از شخص"),
	"sales": ("فروش و مشتریان", "گزارش فروش، پیش‌فاکتورهای در انتظار و سابقه مشتری"),
	"purchase": ("خرید و تأمین‌کنندگان", "گزارش خرید، سفارش‌های دیرکرده و مقایسه قیمت‌ها"),
	"stock": ("انبار", "کالاهای زیر حداقل و پیشنهاد انتقال بین انبارها"),
	"hr": ("کارمندان", "کمبود پرونده‌ها و بررسی حضور و مرخصی"),
	"content": ("نوشتن محتوا", "پیش‌نویس پست، ایمیل و توضیحات"),
	"knowledge": ("پاسخ از دانش شرکت", "پاسخ از منبع‌های دانش ایجنت با نام منبع"),
}
# The tools of the switches of the agent
SWITCHES = {"use_web_search": "web_search", "use_image": "image_draft", "self_update": "agent_self_update"}
STYLES = [
	("standard", "Standard"),
	("nuanced", "Nuanced"),
	("creative", "Snappy & Creative"),
	("rigorous", "Slow & Rigorous"),
]
STYLE_PROMPTS = {
	"standard": ("Keep a balanced, professional tone: clear, direct answers with a moderate level of detail.", 0.3),
	"nuanced": ("Give deeply contextualized answers: weigh the perspectives, note the subtleties, use precise language.", 0.5),
	"creative": ("Be brief, lively and engaging: short sentences, expressive words, a dynamic structure.", 0.8),
	"rigorous": ("Put precision and sound logic above all: break complex steps down, give your reasoning, check each "
		"claim, keep a formal tone.", 0.1),
}


class AiSkill(models.Model):
	_name = "veron.ai.skill"
	_description = "AI Skill"
	_order = "sequence, name"

	name = fields.Char(required=True, translate=True)
	code = fields.Char(readonly=True, copy=False, help="Of the skills the program comes with")
	sequence = fields.Integer(default=10)
	active = fields.Boolean(default=True)
	icon = fields.Char(default="fa-magic", help="A Font Awesome icon, e.g. fa-search")
	description = fields.Char(translate=True)
	instructions = fields.Text(translate=True, help="What the agent is told about this skill: its purpose, its rules, "
		"the steps of the work")
	tool_ids = fields.Many2many("veron.ai.tool", string="Tools")
	available = fields.Boolean(compute="_compute_available", help="All its tools exist in this database")
	agent_count = fields.Integer(compute="_compute_agent_count")

	_code_unique = models.Constraint("unique(code)", "A skill of the program is made once.")

	@api.depends("tool_ids")
	def _compute_available(self):
		for skill in self:
			skill.available = all(registry.get(t.code) and registry.get(t.code).available(self.env) for t in skill.tool_ids)

	def _compute_agent_count(self):
		for skill in self:
			skill.agent_count = self.env["veron.ai.agent"].search_count([("skill_ids", "in", skill.id)])

	@api.model
	def _setup_builtin(self):
		"""The skills of the program, made or brought up to date; a skill a manager changed keeps its text"""
		Tool = self.env["veron.ai.tool"]
		Tool._sync()
		existing = {s.code: s for s in self.with_context(active_test=False).search([("code", "!=", False)])}
		# On a new database Persian is turned on once every module is loaded (veron.iran); until then the names stay
		# English and are given their Persian then, by the same steps
		persian = bool(self.env["res.lang"].search_count([("code", "=", "fa_IR")]))
		for sequence, (code, (name, icon, codes, instructions)) in enumerate(BUILTIN.items(), 1):
			tools = Tool._by_codes(codes)
			if code in existing:
				skill = existing[code]
				skill.tool_ids = [(6, 0, tools.ids)]
				# Made before their Persian was given: given now, unless a manager renamed them
				if persian and skill.with_context(lang="fa_IR").name == name:
					skill.update_field_translations("name", {"fa_IR": FA[code][0]})
				if not skill.description:
					skill.with_context(lang="en_US").description = FA[code][1]
				continue
			name_fa, description_fa = FA[code]
			# The description is for the people of the program, in Persian; the instructions are for the model
			skill = self.with_context(lang="en_US").create({"code": code, "name": name, "icon": icon,
				"description": description_fa, "instructions": instructions, "sequence": sequence * 10,
				"tool_ids": [(6, 0, tools.ids)]})
			if persian:
				skill.update_field_translations("name", {"fa_IR": name_fa})

	def _prompt(self):
		return "\n".join(f"Skill «{skill.name}»: {skill.instructions}" for skill in self if skill.instructions)


class AiAgentSkills(models.Model):
	_inherit = "veron.ai.agent"

	image_128 = fields.Image("Picture", max_width=256, max_height=256)
	skill_ids = fields.Many2many("veron.ai.skill", "veron_ai_agent_skill_rel", "agent_id", "skill_id", "Skills",
		help="Each skill brings its instructions and its tools; without skills the agent only informs")
	use_web_search = fields.Boolean("Web Search", help="Searches the internet through the web search provider")
	use_image = fields.Boolean("Generate Images", help="Makes images through the image provider, as drafts")
	self_update = fields.Boolean("Self Update", help="Proposes changes to its own instructions and skills, which a "
		"manager applies")
	response_style = fields.Selection(STYLES, default="standard", required=True)
	restrict_to_sources = fields.Boolean("Restrict Answers to Sources",
		help="Answers only from its active knowledge sources; says so when they do not have the answer")
	skill_tags = fields.Char(compute="_compute_skill_tags")

	@api.depends("skill_ids.name")
	def _compute_skill_tags(self):
		for agent in self:
			agent.skill_tags = ", ".join(agent.skill_ids.mapped("name"))

	@api.model_create_multi
	def create(self, vals_list):
		agents = super().create(vals_list)
		agents._sync_skill_grants()
		return agents

	def write(self, vals):
		result = super().write(vals)
		if {"skill_ids", *SWITCHES} & set(vals):
			self._sync_skill_grants()
		return result

	def _skill_codes(self):
		self.ensure_one()
		codes = set(self.skill_ids.tool_ids.mapped("code"))
		codes |= {code for name, code in SWITCHES.items() if self[name]}
		if "knowledge_ids" in self._fields and self.knowledge_ids.filtered("active"):
			codes.add("knowledge_sources")
		return codes

	def _sync_skill_grants(self):
		"""The tools of the skills and the switches granted; those given by a skill alone and no longer wanted are
		turned off. A tool a manager granted by hand stays."""
		Grant = self.env["veron.ai.agent.tool"].sudo()
		Tool = self.env["veron.ai.tool"].sudo()
		for agent in self:
			wanted = agent._skill_codes()
			grants = {g.tool_id.code: g for g in agent.with_context(active_test=False).grant_ids}
			for code in wanted:
				grant = grants.get(code)
				if grant:
					if not grant.active and grant.from_skill:
						grant.active = True
					continue
				tool = Tool._by_codes(code)[:1]
				if not tool:
					continue
				level = str(min(int(agent.authority_level), int(tool.level)))
				Grant.create({"agent_id": agent.id, "tool_id": tool.id, "level": level, "from_skill": True})
			for code, grant in grants.items():
				if grant.from_skill and grant.active and code not in wanted:
					grant.active = False

	def _style_prompt(self):
		self.ensure_one()
		text, _temperature = STYLE_PROMPTS.get(self.response_style or "standard", STYLE_PROMPTS["standard"])
		return text

	def _temperature(self):
		self.ensure_one()
		return STYLE_PROMPTS.get(self.response_style or "standard", STYLE_PROMPTS["standard"])[1]


class AiAgentToolFromSkill(models.Model):
	_inherit = "veron.ai.agent.tool"

	from_skill = fields.Boolean("Given by a Skill", readonly=True,
		help="Granted because of the agent's skills or switches; turned off when they no longer need it")

	@api.constrains("level", "agent_id")
	def _check_skill_level(self):
		for grant in self.filtered("from_skill"):
			if int(grant.level) > int(grant.agent_id.authority_level):
				raise ValidationError(_("A tool cannot have more authority than its agent."))


class AiAgentButtons(models.Model):
	_inherit = "veron.ai.agent"

	def action_open_card(self):
		"""The card of an agent opens its chat, or its configuration while it is off"""
		self.ensure_one()
		if self.enabled:
			return self.action_open_chat()
		return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form"}

	def _open_wizard(self, model, title):
		self.ensure_one()
		wizard = self.env[model].create({"agent_id": self.id})
		return {"type": "ir.actions.act_window", "res_model": model, "res_id": wizard.id, "view_mode": "form",
			"target": "new", "name": title}

	def action_add_knowledge(self):
		return self._open_wizard("veron.ai.knowledge.add", _("Add Sources"))

	def action_add_trigger(self):
		return self._open_wizard("veron.ai.trigger.add", _("When Should Your Agent Be Triggered?"))


class VeronIran(models.AbstractModel):
	_inherit = "veron.iran"

	@api.model
	def _apply(self):
		"""Persian is on now: the skills made before it get their Persian names"""
		result = super()._apply()
		self.env["veron.ai.skill"].sudo()._setup_builtin()
		return result
