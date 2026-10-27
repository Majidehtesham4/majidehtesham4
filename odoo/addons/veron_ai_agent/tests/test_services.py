import io

from odoo.tests import TransactionCase, tagged

from ..services import files, redact, schema


@tagged("post_install", "-at_install")
class TestServices(TransactionCase):
	def test_schema_refuses_what_is_not_declared(self):
		spec = schema.strict_object({"model": {"type": "string", "maxLength": 10},
			"limit": {"type": "integer", "minimum": 1, "maximum": 5}}, ["model"])
		self.assertEqual(schema.validate({"model": "res.partner"[:10], "limit": 3}, spec)["limit"], 3)
		for bad in ({"limit": 2}, {"model": "x", "limit": 9}, {"model": "x", "sql": "drop"}, {"model": 5},
				{"model": "x" * 11}, {"model": "x", "limit": True}):
			with self.assertRaises(schema.SchemaError):
				schema.validate(bad, spec)

	def test_redact_hides_keys(self):
		text = redact.text("key sk-ant-api03-abcdefghijklmnop and Bearer abcdefghijklmnopqrstuvwxyz")
		self.assertNotIn("abcdefghijklmnop", text)
		data = redact.data({"api_key": "secret-value", "nested": {"password": "x", "name": "ok"}})
		self.assertNotIn("secret-value", str(data))
		self.assertEqual(data["nested"]["name"], "ok")

	def test_files_are_checked_by_content(self):
		from PIL import Image

		buffer = io.BytesIO()
		Image.new("RGB", (20, 20), (200, 10, 10)).save(buffer, "PNG")
		png = buffer.getvalue()
		self.assertEqual(files.check(png, ("image",), 10 ** 6), ("image/png", "image"))
		with self.assertRaises(files.FileRefused):
			files.check(b"MZ\x90\x00 an executable", ("image", "pdf"), 10 ** 6)
		with self.assertRaises(files.FileRefused):
			files.check(png, ("image",), 10)
		with self.assertRaises(files.FileRefused):
			files.check(b"%PDF-1.4\n1 0 obj << /JavaScript (app.alert(1)) >> endobj", ("pdf",), 10 ** 6)
		with self.assertRaises(files.FileRefused):
			files.check(b"\x89PNG\r\n\x1a\n not really a picture", ("image",), 10 ** 6)
		# Near-identical photos have near-identical hashes
		buffer2 = io.BytesIO()
		Image.new("RGB", (20, 20), (201, 10, 10)).save(buffer2, "PNG")
		self.assertLessEqual(files.hamming(files.image_dhash(png), files.image_dhash(buffer2.getvalue())), 4)
