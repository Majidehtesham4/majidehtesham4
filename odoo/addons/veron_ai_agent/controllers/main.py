import base64

from markupsafe import Markup

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..services.providers import ProviderError


class AgentChat(http.Controller):
	"""Files of the agent chat. The rest of the chat goes through the models' own checked methods."""

	@http.route("/veron_ai/upload", type="http", auth="user", methods=["POST"])
	def upload(self, agent_id, file, purpose="other", **kw):
		"""A photo, a PDF or a voice message for an agent chat; checked before it is kept"""
		try:
			agent = request.env["veron.ai.agent"].browse(int(agent_id)).exists()
			if not agent or not agent._may_use(request.env.user):
				raise AccessError("You may not use this agent.")
			data = file.read()
			source = request.env["veron.ai.source"]._from_upload(file.filename, data, purpose=purpose)
			result = {"id": source.id, "name": source.name, "kind": source.kind, "transcript": ""}
			if source.kind == "audio":
				try:
					result["transcript"] = source._transcribe()
				except UserError as error:
					result["error"] = str(error)
			return request.make_json_response(result)
		except (UserError, AccessError, ValueError) as error:
			return request.make_json_response({"error": str(error)}, status=400)

	@http.route("/veron_ai/source/<int:source_id>", type="http", auth="user")
	def download(self, source_id, **kw):
		source = request.env["veron.ai.source"].browse(source_id).exists()
		if not source:
			raise request.not_found()
		source.check_access("read")
		data = source._data()
		if not data:
			raise request.not_found()
		return request.make_response(data, headers=[("Content-Type", source.mimetype or "application/octet-stream"),
			("Content-Disposition", http.content_disposition(source.name)), ("X-Content-Type-Options", "nosniff")])

	@http.route("/veron_ai/speak", type="jsonrpc", auth="user")
	def speak(self, message_id):
		"""The answer read aloud by the text-to-speech provider, when one is set"""
		message = request.env["veron.ai.message"].browse(int(message_id)).exists()
		if not message:
			return {"error": "not found"}
		message.check_access("read")
		provider = request.env["veron.ai.provider"]._get("tts")
		if not provider:
			return {"browser": True}
		text = Markup(message.body_html or "").striptags()
		try:
			audio, mimetype = provider._adapter().speak(text[:3000], provider.language or "fa")
		except ProviderError as error:
			return {"error": error.text(request.env)}
		return {"audio": base64.b64encode(audio).decode(), "mimetype": mimetype}
