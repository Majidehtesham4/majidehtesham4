{
	"name": "ERP-VERON AI Agents",
	"summary": "Business agents: a library of roles, tools with authority levels, schedules, runs, approvals, a supervisor, and a chat with text, voice and photos",
	"description": """
Agents that do company work inside Odoo, under the control of a manager:

- A library of ready roles (finance, purchase and inventory, sales and website, HR and operations,
  supervisors, the manager's morning report, the company knowledge), each made of small reusable tools
- Each agent: its goal, companies, responsible and supervising person, the user it runs as, its tools
  with their own authority and limits, the data it may read, working hours, manual, scheduled or event
  runs, its report destinations and its error policy
- Four authority levels: read and report; suggest; make drafts and ask approval; act automatically,
  per tool, within amount, company, record type and hour limits. Posting, payments, bank details,
  deleting, closing a period, legal reports, publishing and contacting outside always wait for a person
  unless a manager sets an explicit, limited rule
- Every run recorded: who started it, with whose rights, its inputs, each tool call and the gate's
  decision, its output, findings, errors, linked records and approvers; retries do not redo actions
- A supervisor agent splits work into tasks for its delegates, reviews and explains, and refers to a
  person; it cannot change any access or approve anything
- A chat with text, voice messages (speech-to-text, checked by the person before use) and photos or
  PDFs (vision/OCR), with answers read aloud
- Replaceable providers: language model, vision, speech, text to speech, image generation, web search,
  antivirus. Without them the agents run their fixed steps; ai_claude_anthropic adds Claude
""",
	"version": "19.0.1.2.0",
	"category": "Productivity",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["base", "mail", "web", "resource", "product", "veron_core"],
	"data": [
		"security/ai_security.xml",
		"security/ir.model.access.csv",
		"data/ai_data.xml",
		"data/ai_roles.xml",
		"data/providers.xml",
		"data/intents.xml",
		"report/run_report.xml",
		"views/agent_views.xml",
		"views/run_views.xml",
		"views/settings_views.xml",
		"views/team_wizard_views.xml",
		"views/intent_views.xml",
	],
	"assets": {
		"web.assets_backend": [
			"veron_ai_agent/static/src/chat/chat.js",
			"veron_ai_agent/static/src/chat/assistant.js",
			"veron_ai_agent/static/src/chat/chat.xml",
			"veron_ai_agent/static/src/chat/chat.scss",
		],
	},
	"installable": True,
	"application": True,
}
