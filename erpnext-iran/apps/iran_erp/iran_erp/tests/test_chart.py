from unittest import TestCase

from iran_erp.accounts.chart import (
	COMPANY_DEFAULTS,
	PURCHASE_VAT_ACCOUNT,
	SALES_VAT_ACCOUNT,
	get_chart_tree,
)

ROOT_TYPES = {"Asset", "Liability", "Equity", "Income", "Expense"}
METADATA = {"account_number", "account_type", "root_type", "is_group"}


def walk(tree, root_type=None):
	for name, node in tree.items():
		if name in METADATA:
			continue
		node_root_type = node.get("root_type", root_type)
		children = {k: v for k, v in node.items() if k not in METADATA}
		yield name, node, node_root_type, bool(children)
		yield from walk(children, node_root_type)


class TestIranChart(TestCase):
	def setUp(self):
		self.accounts = list(walk(get_chart_tree()))

	def test_roots_have_root_types(self):
		roots = get_chart_tree()
		self.assertEqual({node["root_type"] for node in roots.values()}, ROOT_TYPES)

	def test_account_numbers_are_unique(self):
		numbers = [node["account_number"] for _, node, _, _ in self.accounts if "account_number" in node]
		self.assertEqual(len(numbers), len(set(numbers)))

	def test_numbers_follow_their_parent(self):
		def check(tree, parent_number=""):
			for name, node in tree.items():
				if name in METADATA:
					continue
				number = node.get("account_number", "")
				if parent_number and number:
					self.assertTrue(number.startswith(parent_number), f"{number} {name}")
				check(node, number or parent_number)

		check(get_chart_tree())

	def test_default_accounts_exist_as_leaves(self):
		leaves = {node.get("account_number"): node for _, node, _, is_group in self.accounts if not is_group}
		for fieldname, number in {
			**COMPANY_DEFAULTS,
			"sales": SALES_VAT_ACCOUNT,
			"purchase": PURCHASE_VAT_ACCOUNT,
		}.items():
			self.assertIn(number, leaves, fieldname)
		self.assertEqual(leaves[SALES_VAT_ACCOUNT].get("account_type"), "Tax")
		self.assertEqual(leaves[PURCHASE_VAT_ACCOUNT].get("account_type"), "Tax")

	def test_receivable_and_payable_sit_under_the_right_root(self):
		for _, node, root_type, _ in self.accounts:
			if node.get("account_type") == "Receivable":
				self.assertEqual(root_type, "Asset")
			if node.get("account_type") in ("Payable", "Stock Received But Not Billed"):
				self.assertEqual(root_type, "Liability")
			if node.get("account_type") == "Income Account":
				self.assertEqual(root_type, "Income")
