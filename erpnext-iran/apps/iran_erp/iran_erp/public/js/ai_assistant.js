// Chat panel for the AI assistant. Questions run in a background job; the panel polls for the answer.

frappe.provide("iran_erp.ai");

iran_erp.ai.Panel = class {
	constructor() {
		this.previous_request = null;
		this.busy = false;
		this.files = [];
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
				<div class="iran-ai-files"></div>
				<div class="iran-ai-input">
					<button class="btn btn-default btn-sm iran-ai-attach" title="${__(
						"Attach a bank statement or an invoice"
					)}">${frappe.utils.icon("attachment", "sm")}</button>
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
		this.$panel.find(".iran-ai-attach").on("click", () => this.attach());
		this.$files = this.$panel.find(".iran-ai-files");
		this.$files.on("click", ".iran-ai-file-remove", (e) => {
			this.files.splice(Number($(e.currentTarget).data("index")), 1);
			this.render_files();
		});
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

	attach() {
		new frappe.ui.FileUploader({
			allow_multiple: true,
			make_attachments_public: false,
			restrictions: { allowed_file_types: [".csv", ".xlsx", ".pdf", "image/*"] },
			on_success: (file) => {
				if (this.files.length < 5) this.files.push(file);
				this.render_files();
			},
		});
	}

	render_files() {
		this.$files.empty();
		this.files.forEach((file, index) => {
			const $chip = $(`<span class="iran-ai-file"></span>`).text(file.file_name);
			$chip.append(
				`<button class="btn btn-xs iran-ai-file-remove" data-index="${index}">${frappe.utils.icon("x", "xs")}</button>`
			);
			this.$files.append($chip);
		});
	}

	reset() {
		this.previous_request = null;
		this.files = [];
		this.render_files();
		this.$messages.empty();
		this.add_message(
			"assistant",
			__(
				"Hello! I can look up records, run reports, prepare draft documents and web pages, export to Excel, reconcile a bank statement, and turn a supplier invoice image into a draft purchase invoice. What do you need?"
			)
		);
	}

	add_message(role, text, actions, files) {
		const $msg = $(`<div class="iran-ai-msg iran-ai-${role}"></div>`);
		if (role === "assistant") {
			$msg.html(this.render_markdown(text));
		} else {
			$msg.text(text);
		}
		(files || []).forEach((file) =>
			$msg.append($(`<div class="iran-ai-msg-file"></div>`).text(`📎 ${file.file_name}`))
		);
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
		let question = (this.$input.val() || "").trim();
		if ((!question && !this.files.length) || this.busy) return;
		if (!question) question = __("Please process the attached file.");
		const files = this.files;
		this.files = [];
		this.render_files();
		this.busy = true;
		this.$input.val("");
		this.add_message("user", question, null, files);
		const $thinking = this.add_message("assistant", __("Thinking…"));
		$thinking.addClass("iran-ai-thinking");

		frappe
			.xcall("iran_erp.ai.api.ask", {
				question,
				previous_request: this.previous_request,
				files: files.map((f) => f.file_url),
			})
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
				// A failed request still carries the conversation, so "try again" works
				this.previous_request = request_name;
				if (r.status === "Done") {
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
	} else if (!frappe.boot.iran_ai_enabled && frappe.boot.iran_ai_can_configure && !iran_erp.ai.setup_button) {
		// Not set up yet: the same button leads administrators to the settings
		iran_erp.ai.setup_button = $(`
			<button class="iran-ai-launcher btn btn-default" title="${__("AI Assistant")}">
				${frappe.utils.icon("sparkles", "md")}<span>${__("AI Assistant")}</span>
			</button>`)
			.appendTo(document.body)
			.on("click", () =>
				frappe.msgprint({
					title: __("AI Assistant"),
					message: __(
						"The assistant needs an OpenRouter API key. Enter the key in AI Assistant Settings, tick Enabled, save, then reload the page."
					),
					primary_action: {
						label: __("Open AI Assistant Settings"),
						action: () => {
							frappe.hide_msgprint();
							frappe.set_route("Form", "Iran AI Settings");
						},
					},
				})
			);
	}
});
