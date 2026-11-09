import logging

from odoo import api, models
from odoo.exceptions import UserError

from .s3 import S3Error
from .storage import PREFIX

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
	_inherit = "ir.attachment"

	@api.model
	def _storage(self):
		if self.env.context.get("veron_storage_as_file"):
			return "file"
		return super()._storage()

	@api.model
	def _get_storage_domain(self):
		if self._storage() == "s3":
			return self.env["veron.storage.s3"]._to_move_domain()
		return super()._get_storage_domain()

	@api.model
	def _get_path(self, bin_data, sha):
		if self._storage() == "s3":
			storage = self.env["veron.storage.s3"]._current()
			if storage:
				return PREFIX + storage._key(sha), None
		return super()._get_path(bin_data, sha)

	@api.model
	def _file_write(self, bin_value, checksum):
		if self._storage() != "s3" or not self.env["veron.storage.s3"]._current():
			return super()._file_write(bin_value, checksum)
		fname, _path = self._get_path(bin_value, checksum)
		try:
			self.env["veron.storage.s3"]._current()._client().put(fname[len(PREFIX):], bin_value)
		except S3Error as error:
			raise UserError(str(error)) from error
		return fname

	@api.model
	def _file_read(self, fname, size=None):
		if not fname.startswith(PREFIX):
			return super()._file_read(fname, size)
		storage = self.env["veron.storage.s3"]._for(fname)
		try:
			data = storage._client().get(fname[len(PREFIX):])
		except (S3Error, UserError) as error:
			_logger.warning("S3 file %s not read: %s", fname, error)
			return b""
		return data[:size] if size else data

	@api.model
	def _file_delete(self, fname):
		if not fname.startswith(PREFIX):
			return super()._file_delete(fname)
		# Removed later, once no attachment uses it: this transaction may still be rolled back
		self.env["veron.storage.s3.garbage"].sudo().create({"fname": fname})
		return None

	@api.autovacuum
	def _gc_file_store(self):
		# The files left on the disk by those moved to the storage are collected as Odoo collects them
		if self._storage() == "s3":
			return super(IrAttachment, self.with_context(veron_storage_as_file=True))._gc_file_store()
		return super()._gc_file_store()

	def _to_http_stream(self):
		if self.store_fname and self.store_fname.startswith(PREFIX):
			from odoo.http import Stream

			data = self.raw
			return Stream(type="data", data=data, mimetype=self.mimetype, download_name=self.name, etag=self.checksum,
				public=self.public, last_modified=self.write_date, size=len(data))
		return super()._to_http_stream()
