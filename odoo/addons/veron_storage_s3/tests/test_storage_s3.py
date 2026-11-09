import base64
import datetime
import hashlib
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.s3 import EMPTY, signed_headers

REQUEST = "odoo.addons.veron_storage_s3.models.s3.requests.request"


class FakeBucket:
	"""An S3 bucket in memory, answering as a storage does"""

	def __init__(self):
		self.objects, self.calls = {}, []

	def __call__(self, method, url, data=None, headers=None, timeout=None):
		self.calls.append((method, url, headers))
		assert headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/")
		key = url.split("/bucket/", 1)[1].split("?")[0] if "/bucket/" in url else ""
		response = MagicMock(status_code=200, content=b"", text="")
		if method == "PUT":
			assert headers["x-amz-content-sha256"] == hashlib.sha256(data).hexdigest()
			self.objects[key] = data
		elif method in ("GET", "HEAD") and key:
			if key in self.objects:
				response.content = self.objects[key]
			else:
				response.status_code = 404
		elif method == "DELETE":
			self.objects.pop(key, None)
			response.status_code = 204
		return response


@tagged("post_install", "-at_install")
class TestStorageS3(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.storage = cls.env["veron.storage.s3"].create({"name": "آروان", "endpoint": "https://s3.example.ir",
			"bucket": "bucket", "access_key": "AK", "secret_key": "SK", "folder": "erp"})

	def setUp(self):
		super().setUp()
		self.bucket = FakeBucket()
		patcher = patch(REQUEST, side_effect=self.bucket)
		patcher.start()
		self.addCleanup(patcher.stop)

	def attach(self, data, name="a.txt"):
		return self.env["ir.attachment"].create({"name": name, "datas": base64.b64encode(data)})

	def test_signature(self):
		"""The example of Amazon's documentation for Signature Version 4 (GET Object with a range)"""
		headers = signed_headers("GET", "https://examplebucket.s3.amazonaws.com/test.txt", "us-east-1",
			"AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", EMPTY, {"Range": "bytes=0-9"},
			now=datetime.datetime(2013, 5, 24, tzinfo=datetime.UTC))
		self.assertIn("SignedHeaders=host;range;x-amz-content-sha256;x-amz-date", headers["authorization"])
		self.assertTrue(headers["authorization"].endswith(
			"Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))

	def test_files_on_the_storage(self):
		before = self.attach(b"on the disk")
		self.assertFalse(before.store_fname.startswith("s3://"))
		self.storage.action_use()
		self.assertEqual(self.env["ir.config_parameter"].get_param("ir_attachment.location"), "s3")
		new = self.attach(b"on the storage")
		self.assertTrue(new.store_fname.startswith("s3://erp/"))
		self.assertEqual(self.bucket.objects[new.store_fname[5:]], b"on the storage")
		new.invalidate_recordset()
		self.assertEqual(new.raw, b"on the storage", "read back from the storage")
		self.assertEqual(before.raw, b"on the disk", "those not moved yet are read from the disk")
		self.assertGreaterEqual(self.storage.on_disk, 1)
		self.storage.action_move(limit=100000)
		before.invalidate_recordset()
		self.assertTrue(before.store_fname.startswith("s3://"))
		self.assertEqual(before.raw, b"on the disk")
		stream = new._to_http_stream()
		self.assertEqual((stream.type, stream.data), ("data", b"on the storage"))

	def test_removed_once_unused(self):
		self.storage.action_use()
		first, second = self.attach(b"same"), self.attach(b"same", "b.txt")
		self.assertEqual(first.store_fname, second.store_fname, "kept once by its content")
		key = first.store_fname[5:]
		first.unlink()
		self.env["veron.storage.s3.garbage"]._gc_s3()
		self.assertIn(key, self.bucket.objects, "still used by the other")
		second.unlink()
		self.assertIn(key, self.bucket.objects, "not removed in the transaction that may be rolled back")
		self.env["veron.storage.s3.garbage"]._gc_s3()
		self.assertNotIn(key, self.bucket.objects)
		self.assertFalse(self.env["veron.storage.s3.garbage"].search([]))

	def test_stopped(self):
		self.storage.action_use()
		kept = self.attach(b"kept there")
		self.storage.action_stop()
		self.assertEqual(self.env["ir.config_parameter"].get_param("ir_attachment.location"), "file")
		self.assertFalse(self.attach(b"back on the disk").store_fname.startswith("s3://"))
		kept.invalidate_recordset()
		self.assertEqual(kept.raw, b"kept there", "still read from the storage")

	def test_unreachable_not_used(self):
		self.storage.secret_key = False
		with self.assertRaises(UserError):
			self.storage.action_use()
		self.assertFalse(self.storage.in_use)
