// Chat panel for the AI assistant. Questions run in a background job; the panel polls for the answer.

frappe.provide("iran_erp.ai");

iran_erp.ai.Panel = class {
	constructor() {
		this.previous_request = null;
		this.busy = false;
		this.make();
	}

	make() {
		this.$button = $(`
			<button class="iran-ai-launcher btn btn-primary" title="${__("AI Assistant")}">
				${frappe.utils.icon("sparkles", "md")}<span>${__("AI Assistant")}</span>
			</button>`).appendTo(document.body);

		this.$panel = $(`
			<div class="iran-ai-panel" dir="rtl" style="display:none">
				<div class="iran-ai-header">
					<div class="iran-ai-title">${frappe.utils.icon("sparkles", "sm")} ${__("AI Assistant")}</div>
					<div class="iran-ai-header-actions">
						<button class="btn btn-xs btn-default iran-ai-new">${__("New Chat")}</button>
						<button class="btn btn-xs btn-default iran-ai-close">${frappe.utils.icon("x", "sm")}</button>
					</div>
				</div>
				<div class="iran-ai-messages"></div>
				<div class="iran-ai-input">
					<textarea rows="2" class="form-control" placeholder="${__(
						"Ask a question or describe what to do…"
					)}"></textarea>
					<button class="btn btn-primary btn-sm iran-ai-send">${__("Send")}</button>
				</div>
			</div>`).appendTo(document.body);

		this.$messages = this.$panel.find(".iran-ai-messages");
		this.$input = this.$panel.find("textarea");

		this.$button.on("click", () => this.toggle(true));
		this.$panel.find(".iran-ai-close").on("click", () => this.toggle(false));
		this.$panel.find(".iran-ai-new").on("click", () => this.reset());
		this.$panel.find(".iran-ai-send").on("click", () => this.send());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
			}
		});
		this.reset();
	}

	toggle(show) {
		this.$panel.toggle(show);
		this.$button.toggle(!show);
		if (show) this.$input.trigger("focus");
	}

	reset() {
		this.previous_request = null;
		this.$messages.empty();
		this.add_message(
			"assistant",
			__(
				"Hello! I can look up records, run reports, prepare draft documents and web pages, and export to Excel. What do you need?"
			)
		);
	}

	add_message(role, text, actions) {
		const $msg = $(`<div class="iran-ai-msg iran-ai-${role}"></div>`);
		if (role === "assistant") {
			$msg.html(this.render_markdown(text));
		} else {
			$msg.text(text);
		}
		(actions || []).forEach((action) => $msg.append(this.render_action(action)));
		this.$messages.append($msg);
		this.$messages.scrollTop(this.$messages[0].scrollHeight);
		return $msg;
	}

	render_markdown(text) {
		// Escape any HTML in the model's reply before markdown, so only markdown formatting survives
		const html = frappe.markdown(frappe.utils.escape_html(text || ""));
		const $html = $("<div>").html(html);
		$html.find("a").each((_, a) => {
			const href = a.getAttribute("href") || "";
			if (!/^(https?:\/\/|\/)/.test(href)) a.removeAttribute("href");
			a.setAttribute("target", "_blank");
		});
		return $html.html();
	}

	render_action(action) {
		const link = action.file_url || action.url;
		if (!link) return "";
		const label = action.file_url
			? `${__("Download")} ${frappe.utils.escape_html(action.file_name || "")}`
			: `${__(action.created || action.updated)}: ${frappe.utils.escape_html(action.name || "")}`;
		const $a = $(`<a class="iran-ai-action" target="_blank"></a>`).attr("href", link).text(label);
		return $("<div>").append($a);
	}

	send() {
		const question = (this.$input.val() || "").trim();
		if (!question || this.busy) return;
		this.busy = true;
		this.$input.val("");
		this.add_message("user", question);
		const $thinking = this.add_message("assistant", __("Thinking…"));
		$thinking.addClass("iran-ai-thinking");

		frappe
			.xcall("iran_erp.ai.api.ask", { question, previous_request: this.previous_request })
			.then((request_name) => this.poll(request_name, $thinking, Date.now()))
			.catch(() => {
				$thinking.remove();
				this.busy = false;
			});
	}

	poll(request_name, $thinking, started) {
		frappe.xcall("iran_erp.ai.api.get_result", { request_name }).then((r) => {
			if (r.status === "Done" || r.status === "Failed") {
				$thinking.remove();
				this.busy = false;
				if (r.status === "Done") {
					this.previous_request = request_name;
					this.add_message("assistant", r.answer, r.actions);
				} else {
					this.add_message("assistant", `⚠️ ${r.error || __("Something went wrong.")}`, r.actions);
				}
				return;
			}
			if (Date.now() - started > 10 * 60 * 1000) {
				$thinking.remove();
				this.busy = false;
				this.add_message("assistant", __("The assistant is taking too long. Please try again."));
				return;
			}
			setTimeout(() => this.poll(request_name, $thinking, started), 2000);
		});
	}
};

$(document).on("app_ready", () => {
	if (frappe.boot.iran_ai_enabled && !iran_erp.ai.panel) {
		iran_erp.ai.panel = new iran_erp.ai.Panel();
	}
});
