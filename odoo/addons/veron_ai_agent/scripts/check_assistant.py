"""The built-in assistant checked against a database's own products and customers: requests for sale invoices are
made up from their real names, in the ways people write them (part of the name, Arabic or Persian letters, digits
in Persian or Latin, counts in words, one to three products, the customer before or after), sent to the assistant,
its questions answered, and the draft compared with what was asked. Nothing is kept: all is undone at the end.

Run inside the program's container by «odoo.ps1 checkassistant <database>». It says what failed, in which way, with
the request: send that output to fix what is left."""

import argparse
import os
import random
import re
import sys

COUNTS = {1: "یک", 2: "دو", 3: "سه", 4: "چهار", 5: "پنج", 6: "شش", 7: "هفت", 8: "هشت", 9: "نه", 10: "ده"}
PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
TEMPLATES = ["{items} برای {partner} فاکتور کن", "فاکتور فروش برای {partner} {items}", "برای {partner} {items} فاکتور بزن",
	"{items} واسه {partner} فاکتور کن"]


def say(text=""):
	print(text, flush=True)


def main():
	os.dup2(sys.stdout.fileno(), sys.stderr.fileno())
	parser = argparse.ArgumentParser()
	parser.add_argument("database")
	parser.add_argument("--requests", type=int, default=200)
	parser.add_argument("--seed", type=int, default=1)
	args = parser.parse_args()

	import logging

	import odoo  # noqa: F401
	from odoo.modules import module as modules
	from odoo.tools import config

	config.parse_config(["-c", "/etc/odoo/odoo.conf"])
	config["db_host"] = os.environ.get("HOST", "db")
	config["db_user"] = os.environ.get("USER", "odoo")
	config["db_password"] = os.environ.get("PASSWORD", "odoo")
	modules.initialize_sys_path()
	logging.getLogger("odoo").setLevel(logging.ERROR)

	from odoo import api
	from odoo.modules.registry import Registry

	from odoo.addons.veron_ai_agent.services import nlu

	random.seed(args.seed)
	registry = Registry(args.database)
	with registry.cursor() as cr:
		admin = api.Environment(cr, 1, {}).ref("base.user_admin")
		env = api.Environment(cr, admin.id, {"lang": "fa_IR"})
		if "account.move" not in env or not env["veron.ai.intent"].search([("code", "=", "sale_invoice_draft")]):
			say("The sale invoice command is not installed here (veron_ai_agent_account).")
			return 1
		products = env["product.product"].search([("sale_ok", "=", True)], limit=3000)
		partners = env["res.partner"].search([("customer_rank", ">", 0), ("name", "!=", False)], limit=3000) or \
			env["res.partner"].search([("is_company", "=", True)], limit=3000)
		products = products.filtered(lambda p: len(nlu.name_words(p.name)) >= 1)
		if not products or not partners:
			say("No products or customers to make requests from.")
			return 1
		words = {p.id: set(nlu.name_words(p.name)) for p in products}
		people = {p.id: set(nlu.name_words(p.name)) for p in partners}
		say(f"Checking {args.requests} requests made from {len(products)} products and {len(partners)} customers...")
		assistant = env.ref("veron_ai_agent.agent_assistant")
		Chat = env["veron.ai.conversation"]

		def written(name):
			"""A product or a name as a person may write it"""
			parts = nlu.normalize(name).split()
			if len(parts) > 3 and random.random() < 0.4:
				parts = parts[: random.randint(3, len(parts) - 1)]
			text = " ".join(parts)
			if random.random() < 0.3:
				text = text.replace("ی", "ي").replace("ک", "ك")
			if random.random() < 0.5:
				text = text.translate(PERSIAN)
			return text

		def expected(said, choices, target, person=False):
			"""«one» when the words name only the target (or it is the base of the others), «ask» otherwise"""
			fits = [i for i, own in choices.items() if said <= own]
			if fits == [target]:
				return "one"
			if [i for i in fits if choices[i] == said] == [target]:
				return "one"
			if not person:
				extra = {i: choices[i] - said for i in fits}
				if all(extra[target] < extra[i] for i in fits if i != target):
					return "one"
			return "ask"

		def what_is_meant(said, target):
			"""What the words of a product say: the target, or the one the others are variants of when the words left
			out what makes the target different («بدون پایه»); a product of the same name stands for it"""
			fits = [i for i, own in words.items() if said <= own]
			extra = {i: words[i] - said for i in fits}
			base = [i for i in fits if all(extra[i] < extra[j] for j in fits if j != i)]
			if base:
				return {i for i in fits if words[i] == words[base[0]]}
			if expected(said, words, target) == "ask":
				# Words that fit several: any of them is what a person may choose
				return set(fits)
			return {i for i in fits if words[i] == words[target]}

		def change(conversation, move, wanted):
			"""A change asked of the draft just made, in the same conversation; what went wrong, or nothing"""
			line = random.choice(move.invoice_line_ids)
			product = line.product_id
			kind = random.choice(["discount", "discount_line", "quantity", "add", "remove"])
			name = written(product.name)
			other = random.choice(list(products))
			percent, count = random.choice([5, 10, 12]), random.choice([4, 6, 7])
			text = {
				"discount": random.choice([f"براش {percent} درصد تخفیف ثبت کن", f"{percent} درصد تخفیف بده"]),
				"discount_line": f"روی {name} {percent} درصد تخفیف بده",
				"quantity": f"تعداد {name} را {count} کن",
				"add": f"{written(other.name)} هم اضافه کن",
				"remove": f"{name} را حذف کن",
			}[kind]
			reply = Chat.veron_chat_send(conversation, text, [], {}, "internal")[-1]
			for _turn in range(3):
				pending = (Chat.browse(conversation).memory or {}).get("pending")
				if not pending or not pending.get("options"):
					break
				ids = [option[0] for option in pending["options"]]
				meant = {product.id, other.id, move.id}
				pick = next((i for i, record_id in enumerate(ids, 1) if record_id in meant), None)
				if not pick:
					break
				reply = Chat.veron_chat_send(conversation, str(pick), [], {}, "internal")[-1]
			move.invalidate_recordset()
			lines = move.invoice_line_ids
			alive = line.exists()
			done = {
				"discount": lambda: all(item.discount == percent for item in lines),
				"discount_line": lambda: bool(alive) and alive.discount == percent,
				"quantity": lambda: bool(alive) and alive.quantity == count,
				"add": lambda: other in lines.product_id,
				"remove": lambda: product not in lines.product_id,
			}[kind]()
			if done:
				counts["changes made"] = counts.get("changes made", 0) + 1
				return ""
			answer = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", reply.get("body_html") or ""))[:160]
			return f"change not made: after «{text}»: {answer}"

		failures, counts = [], {"ok": 0}
		for _number in range(args.requests):
			chosen = random.sample(list(products), k=min(random.choice([1, 1, 2, 3]), len(products)))
			partner = random.choice(list(partners))
			items, wanted = [], []
			for product in chosen:
				quantity = random.choice([1, 1, 2, 3, 5, 10])
				count = random.choice([str(quantity), str(quantity).translate(PERSIAN), COUNTS[quantity]])
				unit = random.choice(["عدد ", "تا ", ""])
				name = written(product.name)
				said = set(nlu.name_words(name))
				items.append(f"{count} {unit}{name}".strip())
				wanted.append((product.id, quantity, expected(said, words, product.id), what_is_meant(said, product.id)))
			partner_said = written(partner.name)
			partner_kind = expected(set(nlu.name_words(partner_said)), people, partner.id, person=True)
			title = random.choice(["", "", "آقای ", "خانم "])
			text = random.choice(TEMPLATES).format(items=random.choice([" و ", "، "]).join(items),
				partner=title + partner_said)
			# Undone with each request, like all the rest
			env["veron.ai.agent"].sudo()._setup_assistant()
			assistant.sudo().enabled = True
			before = env["account.move"].search([], order="id desc", limit=1).id
			conversation = Chat.veron_chat_new(assistant.id)["conversation_id"]
			asked, trouble, done, typed = 0, "", set(), 0
			targets = [i for item in wanted for i in item[3]] + [partner.id]
			try:
				reply = Chat.veron_chat_send(conversation, text, [], {}, "internal")[-1]
				for _turn in range(6):
					pending = (Chat.browse(conversation).memory or {}).get("pending")
					if not pending:
						break
					asked += 1
					ids = [option[0] for option in pending.get("options") or []]
					question = nlu.name_words(pending.get("question") or "")
					if pending.get("arg") == "partner_id":
						meant_now = {i for i, own in people.items() if own == people[partner.id]}
					else:
						# The product of the part asked about («برای «...» کدام کالا؟»), else any of the request's
						offered = [w for w in wanted if w[3] & set(ids) and w[0] not in done] or wanted
						item = max(offered, key=lambda w: nlu.name_score(question, env["product.product"].browse(w[0]).name)[0])
						meant_now = item[3] if "«" in (pending.get("question") or "") else set(targets)
						done.add(item[0])
					pick = next((index for index, record_id in enumerate(ids, 1) if record_id in meant_now), None)
					answer = str(pick) if pick else None
					if not answer and asked <= len(targets):
						typed += 1
						# As a person would: the whole name of what was meant, typed
						if pending.get("arg") == "partner_id":
							answer = partner.name
						else:
							part = nlu.name_words(pending.get("question") or text)
							meant = max((env["product.product"].browse(i) for i in targets[:-1] if i not in done),
								key=lambda r: nlu.name_score(part, r.name)[0], default=None)
							answer = meant.name if meant else None
							done.add(meant.id if meant else 0)
					if not answer:
						trouble = "what was meant is not among the choices offered"
						break
					reply = Chat.veron_chat_send(conversation, answer, [], {}, "internal")[-1]
					if pick:
						done.add(ids[pick - 1])
			except Exception as error:  # noqa: BLE001 - said, and the next request is tried
				trouble = f"error: {error}"
			move = env["account.move"].search([("id", ">", before), ("move_type", "=", "out_invoice")], limit=1)
			if not trouble and not move:
				trouble = "no draft: " + re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", reply.get("body_html") or ""))[:200]
			if not trouble:
				got = [(line.product_id.id, line.quantity) for line in move.invoice_line_ids]
				if people.get(move.partner_id.id) != people[partner.id]:
					trouble = f"wrong customer: {move.partner_id.name}"
				elif len(got) != len(wanted) or any(g[0] not in w[3] or g[1] != w[1] for g, w in zip(got, wanted)):
					names = ", ".join(f"{line.product_id.name} x {line.quantity:g}" for line in move.invoice_line_ids)
					meant = ", ".join(f"{env['product.product'].browse(i).name} x {q}" for i, q, _k, _m in wanted)
					trouble = f"wrong lines: {names} (meant: {meant})"
				else:
					# A list too long to show is narrowed by typing the name: one more question each
					needed = sum(1 for item in wanted if item[2] == "ask") + (partner_kind == "ask") + typed
					if asked > needed:
						trouble = f"asked {asked} times where {needed} was needed"
					elif random.random() < 0.4:
						trouble = change(conversation, move, wanted)
			if trouble:
				kind = trouble.split(":")[0].split(" where")[0]
				counts[kind] = counts.get(kind, 0) + 1
				failures.append((text, trouble))
			else:
				counts["ok"] += 1
			cr.rollback()
			env.invalidate_all()
		say("")
		for kind, count in sorted(counts.items(), key=lambda item: -item[1]):
			say(f"  {kind}: {count}")
		for text, trouble in failures[:40]:
			say("")
			say(f"  > {text}")
			say(f"    {trouble}")
		cr.rollback()
	say("")
	say("Nothing was kept.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
