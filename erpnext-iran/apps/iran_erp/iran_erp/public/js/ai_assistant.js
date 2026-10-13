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
		this.setup_voice();
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

	setup_voice() {
		const use_model = frappe.boot.iran_ai_voice === "AI Model" && navigator.mediaDevices?.getUserMedia;
		// Speech recognition is built into Chrome and Edge; other browsers just don't get the button
		const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
		if (!use_model && !Recognition) return;
		this.$mic = $(
			`<button class="btn btn-default btn-sm iran-ai-mic" title="${__("Speak instead of typing")}">${frappe.utils.icon(
				"mic",
				"sm"
			)}</button>`
		).insertAfter(this.$panel.find(".iran-ai-attach"));
		if (use_model) {
			this.$mic.on("click", () => (this.recorder ? this.recorder.stop() : this.record()));
		} else {
			this.$mic.on("click", () => (this.recognition ? this.recognition.stop() : this.listen(Recognition)));
		}
	}

	async record() {
		let stream;
		try {
			stream = await navigator.mediaDevices.getUserMedia({ audio: true });
		} catch (e) {
			frappe.show_alert(
				{
					message: __(
						"The browser did not allow the microphone. Allow it in the address bar; on a server it only works over HTTPS."
					),
					indicator: "orange",
				},
				8
			);
			return;
		}
		const chunks = [];
		this.recorder = new MediaRecorder(stream);
		this.recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
		this.recorder.onstop = async () => {
			stream.getTracks().forEach((track) => track.stop());
			this.recorder = null;
			this.$mic.removeClass("iran-ai-listening").addClass("iran-ai-transcribing").prop("disabled", true);
			try {
				const audio = await to_wav_base64(new Blob(chunks));
				const text = await frappe.xcall("iran_erp.ai.api.transcribe", { audio }, "POST");
				const before = (this.$input.val() || "").trim();
				this.$input.val([before, text].filter(Boolean).join(" ")).trigger("focus");
			} finally {
				this.$mic.removeClass("iran-ai-transcribing").prop("disabled", false);
			}
		};
		this.recorder.start();
		this.$mic.addClass("iran-ai-listening");
	}

	listen(Recognition) {
		const recognition = new Recognition();
		recognition.lang = "fa-IR";
		recognition.interimResults = true;
		recognition.continuous = true;
		const before = (this.$input.val() || "").trim();
		let spoken = "";
		recognition.onresult = (event) => {
			let interim = "";
			for (let i = event.resultIndex; i < event.results.length; i++) {
				const text = event.results[i][0].transcript;
				if (event.results[i].isFinal) spoken += text + " ";
				else interim += text;
			}
			this.$input.val([before, spoken + interim].filter(Boolean).join(" "));
		};
		recognition.onerror = (event) => {
			const messages = {
				"not-allowed": __(
					"The browser did not allow the microphone. Allow it in the address bar; on a server it only works over HTTPS."
				),
				"service-not-allowed": __(
					"The browser did not allow the microphone. Allow it in the address bar; on a server it only works over HTTPS."
				),
				network: __("Speech recognition needs the browser's online speech service, which could not be reached."),
				"no-speech": __("No speech was heard. Try again closer to the microphone."),
			};
			frappe.show_alert({ message: messages[event.error] || event.error, indicator: "orange" }, 8);
		};
		recognition.onend = () => {
			this.recognition = null;
			this.$mic.removeClass("iran-ai-listening");
			this.$input.trigger("focus");
		};
		this.recognition = recognition;
		this.$mic.addClass("iran-ai-listening");
		recognition.start();
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
			const href = local_link(a.getAttribute("href") || "");
			a.setAttribute("href", href);
			if (!/^(https?:\/\/|\/)/.test(href)) a.removeAttribute("href");
			a.setAttribute("target", "_blank");
		});
		return $html.html();
	}

	render_action(action) {
		const link = local_link(action.file_url || action.url || "");
		if (!link) return "";
		const label = action.file_url
			? `${__("Download")} ${frappe.utils.escape_html(action.file_name || "")}`
			: `${__(action.created || action.updated)}: ${frappe.utils.escape_html(action.name || "")}`;
		const $a = $(`<a class="iran-ai-action" target="_blank"></a>`).attr("href", link).text(label);
		return $("<div>").append($a);
	}

	send() {
		if (this.recognition) this.recognition.stop();
		if (this.recorder) this.recorder.stop();
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

// Links to this site's pages made in a background job carry the container's host name (http://frontend/...);
// keep only the path so they open on whatever address the user is on
function local_link(href) {
	const match = /^https?:\/\/[^/]+(\/(desk|app|files|private|api)\/.*)$/.exec(href);
	return match ? match[1] : href;
}

// Models take audio as WAV; record in whatever the browser offers and convert to 16 kHz mono
async function to_wav_base64(blob) {
	const decoded = await new AudioContext().decodeAudioData(await blob.arrayBuffer());
	const rate = 16000;
	const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * rate), rate);
	const source = offline.createBufferSource();
	source.buffer = decoded;
	source.connect(offline.destination);
	source.start();
	const samples = (await offline.startRendering()).getChannelData(0);

	const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
	const text = (offset, value) => [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
	text(0, "RIFF");
	view.setUint32(4, 36 + samples.length * 2, true);
	text(8, "WAVEfmt ");
	view.setUint32(16, 16, true);
	view.setUint16(20, 1, true);
	view.setUint16(22, 1, true);
	view.setUint32(24, rate, true);
	view.setUint32(28, rate * 2, true);
	view.setUint16(32, 2, true);
	view.setUint16(34, 16, true);
	text(36, "data");
	view.setUint32(40, samples.length * 2, true);
	samples.forEach((sample, i) => {
		const clipped = Math.max(-1, Math.min(1, sample));
		view.setInt16(44 + i * 2, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true);
	});

	const bytes = new Uint8Array(view.buffer);
	let binary = "";
	for (let i = 0; i < bytes.length; i += 0x8000) {
		binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
	}
	return btoa(binary);
}

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
						"The assistant needs an API key from an AI provider. Enter the key in AI Assistant Settings, tick Enabled, save, then reload the page."
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
