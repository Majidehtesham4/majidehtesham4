{
	"name": "ERP-VERON Social Posting",
	"summary": "Post to Telegram, Bale and Eitaa channels, now or at a set time",
	"description": """
Posts with text and a picture, to one channel or several at once, now or scheduled:

- Bale (bale.ai) and Eitaa (through Eitaayar): reachable from servers in Iran
- Telegram: from a server that reaches api.telegram.org

Each channel's result is kept: posted, or the error the platform gave. The bot of each platform must
be an administrator of the channel.
""",
	"version": "19.0.1.0.0",
	"category": "Marketing/Social Marketing",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mail", "veron_core"],
	"data": [
		"security/social_security.xml",
		"security/ir.model.access.csv",
		"data/social_cron.xml",
		"views/social_views.xml",
	],
	"installable": True,
	"application": True,
}
