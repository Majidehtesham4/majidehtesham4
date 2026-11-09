from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .s3 import Client, S3Error

PREFIX = "s3://"


class StorageS3(models.Model):
	"""The S3 storage of the program's files; one is in use at a time"""

	_name = "veron.storage.s3"
	_description = "S3 Storage"

	name = fields.Char(required=True, default="S3")
	endpoint = fields.Char("Address", required=True, help="e.g. https://s3.ir-thr-at1.arvanstorage.ir")
	region = fields.Char(default="us-east-1", required=True, help="The storage's region; for most Iranian storages «us-east-1» or as they say")
	bucket = fields.Char(required=True)
	access_key = fields.Char(required=True, groups="base.group_system")
	secret_key = fields.Char(groups="base.group_system", copy=False)
	folder = fields.Char(default=lambda self: self.env.cr.dbname, help="The files of this database go under this folder of the bucket")
	in_use = fields.Boolean("New Files Kept Here", readonly=True, copy=False)
	on_disk = fields.Integer("Files Still on the Disk or in the Database", compute="_compute_counts")
	on_storage = fields.Integer("Files on the Storage", compute="_compute_counts")

	def _compute_counts(self):
		Attachment = self.env["ir.attachment"].sudo().with_context(active_test=False)
		on_storage = Attachment.search_count([("store_fname", "=like", PREFIX + "%"), *self._all_fields()])
		on_disk = Attachment.search_count(self._to_move_domain())
		for storage in self:
			storage.on_storage, storage.on_disk = on_storage, on_disk

	@staticmethod
	def _all_fields():
		# Attachments of binary fields too, which a search leaves out by default
		return ["|", ("res_field", "=", False), ("res_field", "!=", False)]

	@api.model
	def _to_move_domain(self):
		return [("type", "=", "binary"), "|", ("db_datas", "!=", False), "&", ("store_fname", "!=", False),
			("store_fname", "not like", PREFIX + "%"), *self._all_fields()]

	@api.model
	def _current(self):
		return self.sudo().search([("in_use", "=", True)], limit=1)

	@api.model
	def _for(self, fname):
		"""The storage a file name belongs to: the one in use, or another whose folder it is under"""
		key = fname[len(PREFIX):]
		storages = self.sudo().search([], order="in_use desc, id")
		return next((s for s in storages if key.startswith((s.folder or "").strip("/") + "/")), storages[:1])

	def _client(self):
		self.ensure_one()
		storage = self.sudo()
		if not storage.secret_key:
			raise UserError(_("The secret key of the storage %s is not entered.", self.name))
		return Client(storage.endpoint, storage.region, storage.bucket, storage.access_key, storage.secret_key)

	def _key(self, checksum):
		folder = (self.folder or "").strip("/")
		return "/".join(filter(None, [folder, checksum[:2], checksum]))

	def action_test(self):
		self.ensure_one()
		client = self._client()
		key = self._key("veron-test")
		try:
			client.check_bucket()
			client.put(key, b"ERP-VERON")
			back = client.get(key)
			client.delete(key)
		except S3Error as error:
			raise UserError(str(error)) from error
		if back != b"ERP-VERON":
			raise UserError(_("The storage gave back something else than what was put."))
		return {"type": "ir.actions.client", "tag": "display_notification",
			"params": {"message": _("The storage is reachable: a file was put, read and removed."), "type": "success"}}

	def action_use(self):
		"""New files kept on this storage, after it is tried"""
		self.ensure_one()
		self.action_test()
		self.sudo().search([("id", "!=", self.id)]).in_use = False
		self.in_use = True
		self.env["ir.config_parameter"].sudo().set_param("ir_attachment.location", "s3")

	def action_stop(self):
		self.in_use = False
		if not self._current():
			self.env["ir.config_parameter"].sudo().set_param("ir_attachment.location", "file")

	def action_move(self, limit=500):
		"""A part of the files on the disk or in the database moved to the storage; the scheduled action moves the rest"""
		if not self._current():
			raise UserError(_("No storage is in use."))
		attachments = self.env["ir.attachment"].sudo().with_context(active_test=False).search(self._to_move_domain(), limit=limit)
		attachments._migrate()
		return len(attachments)

	@api.model
	def _cron_move(self):
		if self._current():
			self.action_move(limit=2000)


class StorageS3Garbage(models.Model):
	"""Files no attachment may use any more, removed from the storage once that is committed and checked"""

	_name = "veron.storage.s3.garbage"
	_description = "S3 Files to Remove"

	fname = fields.Char(required=True, index=True)

	@api.autovacuum
	def _gc_s3(self):
		Attachment = self.env["ir.attachment"].sudo().with_context(active_test=False)
		for item in self.search([], limit=5000):
			if not Attachment.search_count([("store_fname", "=", item.fname), "|", ("res_field", "=", False),
					("res_field", "!=", False)]):
				storage = self.env["veron.storage.s3"]._for(item.fname)
				try:
					storage._client().delete(item.fname[len(PREFIX):])
				except (S3Error, UserError):
					continue
			item.unlink()
