"""A small S3 client: objects put, got, checked and deleted with requests signed by AWS Signature Version 4,
on path-style addresses (https://endpoint/bucket/key), which every S3 storage accepts"""

import datetime
import hashlib
import hmac
from urllib.parse import quote, urlsplit

import requests

TIMEOUT = 60
EMPTY = hashlib.sha256(b"").hexdigest()


class S3Error(Exception):
	pass


def _hmac(key, text):
	return hmac.new(key, text.encode(), hashlib.sha256).digest()


def signed_headers(method, url, region, access_key, secret_key, payload_hash, headers=None, now=None):
	"""The headers of a request signed by AWS Signature Version 4 for the service «s3»"""
	now = now or datetime.datetime.now(datetime.UTC)
	stamp, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
	parts = urlsplit(url)
	headers = {key.lower(): str(value).strip() for key, value in (headers or {}).items()}
	headers.update({"host": parts.netloc, "x-amz-date": stamp, "x-amz-content-sha256": payload_hash})
	names = sorted(headers)
	query = "&".join(sorted(
		f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, _sep, v in
		(item.partition("=") for item in parts.query.split("&") if item)))
	canonical = "\n".join([method, quote(parts.path or "/", safe="/-_.~"), query,
		"".join(f"{name}:{headers[name]}\n" for name in names), ";".join(names), payload_hash])
	scope = f"{day}/{region}/s3/aws4_request"
	to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
	key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), day), region), "s3"), "aws4_request")
	signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
	headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
		f"SignedHeaders={';'.join(names)}, Signature={signature}")
	headers.pop("host")
	return headers


class Client:
	def __init__(self, endpoint, region, bucket, access_key, secret_key):
		self.endpoint = endpoint.rstrip("/")
		if "://" not in self.endpoint:
			self.endpoint = "https://" + self.endpoint
		self.region = region or "us-east-1"
		self.bucket = bucket
		self.access_key, self.secret_key = access_key, secret_key

	def _url(self, key=""):
		return f"{self.endpoint}/{quote(self.bucket)}/{quote(key, safe='/-_.~')}" if key else f"{self.endpoint}/{quote(self.bucket)}"

	def request(self, method, key="", data=b"", headers=None, query=""):
		url = self._url(key) + (f"?{query}" if query else "")
		payload = hashlib.sha256(data).hexdigest() if data else EMPTY
		signed = signed_headers(method, url, self.region, self.access_key, self.secret_key, payload, headers)
		try:
			return requests.request(method, url, data=data or None, headers=signed, timeout=TIMEOUT)
		except requests.exceptions.RequestException as error:
			raise S3Error(f"The storage could not be reached: {error}") from error

	@staticmethod
	def _check(response, *ok):
		if response.status_code not in (ok or (200,)):
			raise S3Error(f"The storage answered {response.status_code}: {response.text[:300]}")
		return response

	def put(self, key, data, content_type="application/octet-stream"):
		self._check(self.request("PUT", key, data, {"content-type": content_type}))

	def get(self, key):
		return self._check(self.request("GET", key)).content

	def exists(self, key):
		return self._check(self.request("HEAD", key), 200, 404).status_code == 200

	def delete(self, key):
		self._check(self.request("DELETE", key), 200, 204, 404)

	def check_bucket(self):
		self._check(self.request("GET", query="list-type=2&max-keys=1"))
