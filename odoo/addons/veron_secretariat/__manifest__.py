{
	"name": "ERP-VERON Secretariat",
	"summary": "Letters in and out (دبیرخانه): numbers by Shamsi year, referrals with deadlines, confidential letters, "
		"related letters, printed on the letterhead",
	"description": """
The secretariat of an Iranian organization:

- Incoming, outgoing and internal letters, each numbered when registered in its own series of the Shamsi
  year («۱۴۰۵/و/۱۲» incoming, «۱۴۰۵/ص/۳» outgoing, «۱۴۰۵/د/۷» internal); a registered number is not
  changed
- For an incoming letter, the sender's own number and date; for an outgoing one, who signs it
- Priority (normal, urgent, immediate) and classification (normal, confidential, secret): a confidential or
  secret letter is seen only by who made it, who it is to, who it is referred to and the secretariat
  managers
- Referrals (ارجاع): to a person with an instruction and a deadline, each as a to-do of theirs; done with
  an answer
- Related letters: following up (پیرو), in reference to (عطف), in answer to (بازگشت)
- The letter printed on the letterhead, with its number, date and enclosure; files kept on the letter
""",
	"version": "19.0.1.1.0",
	"category": "Productivity",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mail", "veron_core"],
	"data": [
		"security/security.xml",
		"security/ir.model.access.csv",
		"views/letter_views.xml",
		"report/letter_report.xml",
	],
	"application": True,
	"installable": True,
}
