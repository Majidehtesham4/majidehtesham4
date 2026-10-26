{
	"name": "ERP-VERON PLM",
	"summary": "Engineering changes: new versions of bills of materials, reviewed and approved before use",
	"description": """
Changes to a product's bill of materials go through an engineering change order (ECO):

- The change is made on a new version of the bill of materials, kept apart: production goes on with
  the current one
- The differences with the current version are listed: components added, removed, quantities and
  operations changed
- A manufacturing manager approves; only then the new version replaces the current one
- Each bill of materials keeps its version number and the version it replaced
""",
	"version": "19.0.1.0.0",
	"category": "Manufacturing/Product Lifecycle Management (PLM)",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["mrp", "veron_core"],
	"data": [
		"security/plm_security.xml",
		"security/ir.model.access.csv",
		"data/plm_data.xml",
		"views/plm_views.xml",
	],
	"installable": True,
	"application": True,
}
