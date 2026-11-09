{
	"name": "ERP-VERON S3 Storage",
	"summary": "The program's files (attachments, pictures, documents) kept on an S3 storage: ArvanCloud, ParsPack, MinIO, AWS...",
	"description": """
- The storage's address, region, bucket and keys, entered by the administrator; the secret key is shown to no one
- Turned on, new files go to the storage; the files already there are moved by a button, a part at a time,
  and those not moved yet are still read from the server's disk
- A file is kept once by its content; it is removed from the storage only after no attachment uses it, once the
  transaction that removed it is committed
- Turned off, new files go to the disk again; the files on the storage are still read from it
- Requests signed with AWS Signature Version 4, the way all of these storages accept, with no other library
""",
	"version": "19.0.1.0.0",
	"category": "Hidden/Tools",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["base_setup", "veron_core"],
	"data": [
		"security/ir.model.access.csv",
		"data/cron.xml",
		"views/storage_views.xml",
	],
	"installable": True,
}
