{
	"name": "ERP-VERON WhatsApp",
	"summary": "WhatsApp messages to customers and from them, through WhatsApp's Cloud API, kept on the record",
	"description": """
- The company's WhatsApp Business number, with the key of Meta's Cloud API; the key and the app's secret entered
  by the administrator and kept from everyone else
- Messages sent from a contact or any record with a contact (an invoice, an order...): an approved template of
  WhatsApp with its values from the record, or a free text within 24 hours of the customer's last message, as
  WhatsApp allows
- The customer's answers and the state of each message (sent, delivered, read, failed) come back through the
  webhook, checked by its signature, and are written on the contact
- WhatsApp's servers are not reached from a server in Iran without a route out; the module says so in its errors
""",
	"version": "19.0.1.0.0",
	"category": "Marketing",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mail", "veron_core"],
	"data": [
		"security/whatsapp_security.xml",
		"security/ir.model.access.csv",
		"wizard/composer_views.xml",
		"views/whatsapp_views.xml",
	],
	"installable": True,
	"application": True,
}
