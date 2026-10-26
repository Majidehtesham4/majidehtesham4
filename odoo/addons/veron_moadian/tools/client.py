"""Calls to the Moadian service (API v2 of the tax organization), as its published SDKs make them"""

import uuid

import requests

from . import jose

DEFAULT_URL = "https://tp.tax.gov.ir/requestsmanager/api/v2/"
TIMEOUT = 60


class MoadianError(Exception):
	pass


class Client:
	def __init__(self, base_url, memory_id, private_key_pem, certificate_pem, session=None):
		self.base_url = base_url.rstrip("/") + "/"
		self.memory_id = memory_id
		self.private_key_pem = private_key_pem
		self.certificate_pem = certificate_pem
		self.session = session or requests

	def _call(self, method, path, token=False, **kwargs):
		headers = {"accept": "*/*", "Content-Type": "application/json"}
		if token:
			headers["authorization"] = "Bearer " + self._token()
		response = self.session.request(method, self.base_url + path, headers=headers, timeout=TIMEOUT, **kwargs)
		try:
			body = response.json()
		except ValueError:
			body = {}
		if response.status_code >= 400:
			errors = body.get("errors") if isinstance(body, dict) else None
			message = errors[0].get("message") if errors else (response.text or "")[:300]
			raise MoadianError(f"{response.status_code}: {message}")
		return body

	def _token(self):
		nonce = self._call("GET", "nonce", params={"timeToLive": 30})["nonce"]
		return jose.sign({"nonce": nonce, "clientId": self.memory_id}, self.private_key_pem, self.certificate_pem)

	def server_key(self):
		"""(key id, public key) of the tax organization"""
		key = self._call("GET", "server-information")["publicKeys"][0]
		return key["id"], jose.public_key_from_base64(key["key"])

	def send(self, invoice: dict):
		"""The result of the service for one invoice: its uid and reference number"""
		key_id, public_key = self.server_key()
		packet = jose.encrypt(jose.sign(invoice, self.private_key_pem, self.certificate_pem), public_key, key_id)
		body = self._call("POST", "invoice", token=True, json=[{
			"payload": packet,
			"header": {"requestTraceId": str(uuid.uuid4()), "fiscalId": self.memory_id},
		}])
		result = (body.get("result") or [{}])[0]
		if not result.get("referenceNumber"):
			raise MoadianError(str(result.get("errorCode") or body)[:300])
		return result

	def inquire(self, reference_numbers):
		"""The status of sent invoices by their reference numbers"""
		body = self._call("GET", "inquiry-by-reference-id", token=True, params={"referenceIds": ",".join(reference_numbers)})
		return body if isinstance(body, list) else body.get("result") or body.get("data") or []
