from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAutomation(TransactionCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		Partner = cls.env["res.partner"]
		cls.ali = Partner.create({"name": "آزمون علی", "email": "ali@example.com", "phone": "+989121111111"})
		cls.sara = Partner.create({"name": "آزمون سارا", "email": "sara@example.com"})  # no phone
		cls.template = cls.env["mail.template"].create({
			"name": "خوش‌آمد", "model_id": cls.env.ref("base.model_res_partner").id,
			"subject": "خوش آمدید {{ object.name }}", "body_html": "<p>سلام</p>", "email_to": "{{ object.email }}"})
		cls.campaign = cls.env["veron.automation.campaign"].create({
			"name": "مشتری‌های تازه", "domain": "[('name', 'like', 'آزمون')]"})
		Activity = cls.env["veron.automation.activity"]
		cls.welcome = Activity.create({"campaign_id": cls.campaign.id, "name": "ایمیل خوش‌آمد", "kind": "email",
			"mail_template_id": cls.template.id, "delay_count": 0})
		cls.sms = Activity.create({"campaign_id": cls.campaign.id, "name": "پیامک", "kind": "sms", "parent_id": cls.welcome.id,
			"delay_count": 0, "sms_body": "{{ object.name }} عزیز، کد تخفیف شما YALDA است"})
		cls.call = Activity.create({"campaign_id": cls.campaign.id, "name": "تماس", "kind": "todo", "parent_id": cls.welcome.id,
			"delay_count": 3, "delay_unit": "days", "domain": "[('phone', '!=', False)]"})

	def test_run(self):
		self.campaign.action_start()
		self.assertEqual(set(self.campaign.participant_ids.mapped("res_id")), {self.ali.id, self.sara.id})
		mails = self.env["mail.mail"].search([("model", "=", "res.partner"), ("res_id", "in", (self.ali | self.sara).ids)])
		self.assertEqual(len(mails), 2)
		# Next run: the SMS (no delay); the call waits three days
		self.campaign._run()
		sms = self.env["sms.sms"].search([("number", "=", "+989121111111")])
		self.assertEqual(sms.body, "آزمون علی عزیز، کد تخفیف شما YALDA است")
		sara_trace = self.env["veron.automation.trace"].search([("activity_id", "=", self.sms.id), ("participant_id.res_id", "=", self.sara.id)])
		self.assertEqual(sara_trace.state, "error")  # no phone number
		calls = self.env["veron.automation.trace"].search([("activity_id", "=", self.call.id)])
		self.assertEqual(set(calls.mapped("state")), {"scheduled"})
		# Three days later: the to-do for Ali only (Sara has no phone: condition not met)
		later = fields.Datetime.now() + timedelta(days=3, hours=1)
		with patch("odoo.fields.Datetime.now", return_value=later):
			self.campaign._run()
		self.assertEqual(self.ali.activity_ids[:1].summary, "تماس")
		self.assertFalse(self.sara.activity_ids)
		self.assertEqual(set(self.campaign.participant_ids.mapped("state")), {"done"})

	def test_new_records_join_and_stop(self):
		self.campaign.action_start()
		newcomer = self.env["res.partner"].create({"name": "آزمون رضا", "email": "reza@example.com"})
		self.campaign._run()
		self.assertIn(newcomer.id, self.campaign.participant_ids.mapped("res_id"))
		self.campaign.action_stop()
		self.assertFalse(self.env["veron.automation.trace"].search([("campaign_id", "=", self.campaign.id), ("state", "=", "scheduled")]))
