{
	"name": "ERP-VERON Iranian Website",
	"summary": "Sign-up and login with a mobile number and an SMS code, Persian fonts for the website, Aparat videos, "
		"Neshan maps, podcasts",
	"description": """
- Login and sign-up with a mobile number (ثبت نام و ورود با موبایل): a code of six digits sent by SMS (through
  the company's SMS panel), good for two minutes and five tries; a new number gets a portal account when
  sign-up is open. Internal users log in this way only when the website allows it; their two-factor
  authentication still applies. Codes and login tokens are kept hashed, each used once, and a number or an
  address asking too often is made to wait
- The website in a Persian font that comes with the program (Vazirmatn, Sahel, Shabnam, Samim)
- Blocks for the website builder: an Aparat video (آپارات) and a Neshan map (نقشه نشان), the latter drawn by
  the server with the website's Neshan key, which the visitor never sees
- Podcasts (پادکست): episodes with their audio, a page on the website and an RSS feed for podcast apps
""",
	"version": "19.0.1.0.0",
	"category": "Website/Website",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["website", "auth_signup", "sms", "veron_fonts_iran"],
	"data": [
		"security/ir.model.access.csv",
		"views/website_views.xml",
		"views/login_templates.xml",
		"views/snippets.xml",
		"views/podcast_views.xml",
		"views/podcast_templates.xml",
	],
	"installable": True,
}
