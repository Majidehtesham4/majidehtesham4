import frappe
from frappe.tests import IntegrationTestCase

from iran_erp.inbox import get_inbox


class TestInbox(IntegrationTestCase):
	def test_assigned_tasks_are_counted(self):
		def tasks():
			items = [i for i in get_inbox()["items"] if i["section"] == "tasks"]
			return items[0]["count"] if items else 0

		before = tasks()
		frappe.get_doc(
			{"doctype": "ToDo", "description": "Inbox test", "allocated_to": frappe.session.user}
		).insert()
		self.assertEqual(tasks(), before + 1)

	def test_total_is_the_sum_of_items(self):
		inbox = get_inbox()
		self.assertEqual(inbox["total"], sum(i["count"] for i in inbox["items"]))
		for item in inbox["items"]:
			self.assertIn(item["section"], ("approvals", "drafts", "tasks", "alerts"))
			self.assertTrue(frappe.db.exists("DocType", item["doctype"]))
