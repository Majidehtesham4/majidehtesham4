from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from iran_erp.ai import openrouter
from iran_erp.ai.openrouter import AIError, chat_completion, transcribe_audio

GROQ = frappe._dict(
	provider="Groq",
	api_format=openrouter.OPENAI_FORMAT,
	api_key="gsk_test",
	model="openai/gpt-oss-120b",
	fallback_models=[],
	base_url="https://api.groq.com/openai/v1",
	transcription_model="whisper-large-v3",
)


def fake_response(status: int, data: dict, headers: dict | None = None):
	response = MagicMock(status_code=status, headers=headers or {}, text=str(data))
	response.json.return_value = data
	return response


class TestAIClient(UnitTestCase):
	@patch("iran_erp.ai.openrouter.time.sleep")
	@patch("iran_erp.ai.openrouter.requests.post")
	def test_waits_as_long_as_the_provider_asks(self, post, sleep):
		reply = {"choices": [{"message": {"role": "assistant", "content": "OK"}}]}
		post.side_effect = [
			fake_response(429, {"error": {"message": "rate limit"}}, {"retry-after": "7"}),
			fake_response(200, reply),
		]
		self.assertEqual(chat_completion(GROQ, [{"role": "user", "content": "hi"}]), reply)
		sleep.assert_called_once_with(7.0)
		self.assertEqual(post.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
		self.assertNotIn("models", post.call_args.kwargs["json"])

	@patch("iran_erp.ai.openrouter.requests.post")
	def test_whisper_transcription(self, post):
		post.return_value = fake_response(200, {"text": " سلام "})
		self.assertEqual(transcribe_audio(GROQ, b"RIFF", "کابل"), "سلام")
		self.assertEqual(post.call_args.args[0], "https://api.groq.com/openai/v1/audio/transcriptions")
		self.assertEqual(post.call_args.kwargs["data"]["model"], "whisper-large-v3")
		self.assertEqual(post.call_args.kwargs["data"]["language"], "fa")
		self.assertIn("file", post.call_args.kwargs["files"])

	@patch("iran_erp.ai.openrouter.requests.post")
	def test_errors_are_explained(self, post):
		post.return_value = fake_response(402, {"error": {"message": "Insufficient Balance"}})
		with self.assertRaises(AIError) as error:
			chat_completion(GROQ, [{"role": "user", "content": "hi"}])
		self.assertIn("402", str(error.exception))
		post.return_value = fake_response(413, {"error": {"message": "Request too large"}})
		with self.assertRaises(AIError) as error:
			chat_completion(GROQ, [{"role": "user", "content": "hi"}])
		self.assertIn("413", str(error.exception))
