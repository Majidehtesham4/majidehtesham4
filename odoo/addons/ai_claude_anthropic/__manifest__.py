{
	"name": "Claude for AI Agents",
	"summary": "Anthropic Claude as the language model, the reader of photos and PDFs and the web search of the AI agents",
	"description": """
Claude (Anthropic) behind the provider interface of veron_ai_agent:

- language model with the agent's tools: Claude only names a tool and its arguments; the agent framework
  checks and runs it, so Claude never reaches the database
- reading photos and PDFs into the fields a tool asks for (structured output), kept for a person to check
- web search, only on the sites the provider allows

It needs the official anthropic library (odoo.ps1 ai, or ./veron ai on a server) and a key, entered in
AI Agents, Settings, Providers. Without them it installs and agents keep working with their own steps.
""",
	"version": "19.0.1.0.0",
	"category": "Productivity",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["veron_ai_agent"],
	"data": ["data/providers.xml"],
	"installable": True,
	"application": False,
}
