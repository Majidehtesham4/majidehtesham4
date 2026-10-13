"""Convert between OpenAI chat completions and Anthropic's Messages API.

The assistant builds every conversation in OpenAI's shape; this lets the same conversation go to a
provider that only offers the Anthropic format ("claude_native").
"""

import json
import re

MAX_TOKENS = 8192
DATA_URL = re.compile(r"^data:([\w/+.-]+);base64,(.*)$", re.S)


def to_anthropic_request(model: str, messages: list, tools: list | None) -> dict:
	system = "\n\n".join(m["content"] for m in messages if m["role"] == "system" and m.get("content"))
	turns = []

	def add(role, blocks):
		# The Messages API wants user and assistant turns to alternate, so merge neighbours
		if turns and turns[-1]["role"] == role:
			turns[-1]["content"].extend(blocks)
		else:
			turns.append({"role": role, "content": list(blocks)})

	for message in messages:
		role = message["role"]
		if role == "system":
			continue
		if role == "tool":
			add(
				"user",
				[
					{
						"type": "tool_result",
						"tool_use_id": message.get("tool_call_id"),
						"content": message.get("content") or "",
					}
				],
			)
			continue
		blocks = content_blocks(message.get("content"))
		if role == "assistant":
			for call in message.get("tool_calls") or []:
				function = call.get("function") or {}
				try:
					arguments = json.loads(function.get("arguments") or "{}")
				except ValueError:
					arguments = {}
				blocks.append(
					{
						"type": "tool_use",
						"id": call.get("id"),
						"name": function.get("name"),
						"input": arguments,
					}
				)
		if blocks:
			add("assistant" if role == "assistant" else "user", blocks)

	request = {"model": model, "max_tokens": MAX_TOKENS, "messages": turns}
	if system:
		request["system"] = system
	if tools:
		request["tools"] = [
			{
				"name": tool["function"]["name"],
				"description": tool["function"].get("description", ""),
				"input_schema": tool["function"].get("parameters") or {"type": "object", "properties": {}},
			}
			for tool in tools
		]
		request["tool_choice"] = {"type": "auto"}
	return request


def content_blocks(content) -> list:
	if not content:
		return []
	if isinstance(content, str):
		return [{"type": "text", "text": content}]
	blocks = []
	for part in content:
		kind = part.get("type")
		if kind == "text" and part.get("text"):
			blocks.append({"type": "text", "text": part["text"]})
		elif kind == "image_url":
			source = base64_source((part.get("image_url") or {}).get("url", ""))
			if source:
				blocks.append({"type": "image", "source": source})
		elif kind == "file":
			source = base64_source((part.get("file") or {}).get("file_data", ""))
			if source:
				blocks.append({"type": "document", "source": source})
		elif kind == "input_audio":
			blocks.append({"type": "text", "text": "[audio is not supported by this provider format]"})
	return blocks


def base64_source(data_url: str) -> dict | None:
	match = DATA_URL.match(data_url or "")
	if not match:
		return None
	return {"type": "base64", "media_type": match.group(1), "data": match.group(2)}


def from_anthropic_response(data: dict) -> dict:
	"""An Anthropic Messages response in OpenAI's chat completions shape."""
	if "content" not in data:
		return {}
	text = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
	tool_calls = [
		{
			"id": block.get("id"),
			"type": "function",
			"function": {
				"name": block.get("name"),
				"arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
			},
		}
		for block in data["content"]
		if block.get("type") == "tool_use"
	]
	message = {"role": "assistant", "content": text or None}
	if tool_calls:
		message["tool_calls"] = tool_calls
	usage = data.get("usage") or {}
	return {
		"id": data.get("id"),
		"model": data.get("model"),
		"choices": [{"index": 0, "message": message, "finish_reason": data.get("stop_reason")}],
		"usage": {"total_tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)},
	}
