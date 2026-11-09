{
	"name": "ERP-VERON Exchange Rates",
	"summary": "Rates of the dollar, euro, dirham and others to the rial, fetched from a source on a schedule",
	"description": """
The rates of foreign currencies to the rial, as the currency rates of a company whose currency is the rial:

- A source of rates: Navasan (navasan.tech, with its API key, rates in toman) or any address that answers
  JSON, with the field of each currency in its answer and whether it is in rial or toman
- Fetched by a scheduled action (every few hours, as set) or with a button; the rate of the day is made or
  changed, those of the days before stay
- A rate that cannot be read, or one that moved more than the limit set since the last one, is not used:
  the error is kept on the source and the accountant sees it

The rates are those the source gives; the rate a business must use for its accounts (the Central Bank's,
the market's, the NIMA system's) is the business's choice of source.
""",
	"version": "19.0.1.0.0",
	"category": "Accounting/Accounting",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["account", "veron_core"],
	"data": ["security/ir.model.access.csv", "data/cron.xml", "views/source_views.xml"],
	"installable": True,
}
