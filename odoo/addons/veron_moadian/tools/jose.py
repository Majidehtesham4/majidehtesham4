"""The JOSE packets of the Moadian service: data signed as a JWS (RS256) with the taxpayer's key and
certificate, and an invoice encrypted as a JWE (RSA-OAEP-256, A256GCM) with the public key of the tax
organization, as the published SDKs of the service do."""

import base64
import datetime
import json
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def b64url(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text: str) -> bytes:
	return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _json(value) -> bytes:
	return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def load_private_key(pem: str):
	return serialization.load_pem_private_key(pem.encode(), password=None)


def certificate_x5c(pem: str) -> str:
	"""The certificate in base64 DER, as the x5c header wants it"""
	certificate = x509.load_pem_x509_certificate(pem.encode())
	return base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()


def sign(payload: dict, private_key_pem: str, certificate_pem: str, now=None) -> str:
	"""A compact JWS of the payload"""
	now = now or datetime.datetime.now(datetime.timezone.utc)
	header = {
		"typ": "JWT",
		"x5c": [certificate_x5c(certificate_pem)],
		"sigT": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
		"crit": ["sigT"],
		"cty": "text/plain",
		"alg": "RS256",
	}
	signing_input = f"{b64url(_json(header))}.{b64url(_json(payload))}"
	signature = load_private_key(private_key_pem).sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
	return f"{signing_input}.{b64url(signature)}"


def public_key_from_base64(key: str):
	"""The public key of the tax organization, as server-information gives it (base64 DER)"""
	return serialization.load_der_public_key(base64.b64decode(key))


def encrypt(jws: str, public_key, key_id: str) -> str:
	"""A compact JWE of a signed invoice"""
	header = b64url(_json({"alg": "RSA-OAEP-256", "enc": "A256GCM", "kid": key_id}))
	content_key, iv = os.urandom(32), os.urandom(12)
	encrypted_key = public_key.encrypt(content_key, padding.OAEP(
		mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
	sealed = AESGCM(content_key).encrypt(iv, jws.encode(), header.encode())
	ciphertext, tag = sealed[:-16], sealed[-16:]
	return ".".join((header, b64url(encrypted_key), b64url(iv), b64url(ciphertext), b64url(tag)))


def decrypt(jwe: str, private_key) -> str:
	"""The signed invoice of a JWE; the tax organization does this, here for the tests"""
	header, encrypted_key, iv, ciphertext, tag = jwe.split(".")
	content_key = private_key.decrypt(b64url_decode(encrypted_key), padding.OAEP(
		mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
	return AESGCM(content_key).decrypt(b64url_decode(iv), b64url_decode(ciphertext) + b64url_decode(tag), header.encode()).decode()


def verify(jws: str, certificate_pem: str) -> dict:
	"""The payload of a JWS whose signature matches the certificate"""
	header, payload, signature = jws.split(".")
	certificate = x509.load_pem_x509_certificate(certificate_pem.encode())
	certificate.public_key().verify(b64url_decode(signature), f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
	return json.loads(b64url_decode(payload))


def new_key_and_request(common_name: str, national_id: str, organization: str = ""):
	"""A new RSA 2048 key and the certificate signing request to give the tax organization"""
	from cryptography.hazmat.primitives.asymmetric import rsa
	from cryptography.x509.oid import NameOID

	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	names = [x509.NameAttribute(NameOID.COUNTRY_NAME, "IR"), x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
	if national_id:
		names.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, national_id))
	if organization:
		names.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))
	request = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(names)).sign(key, hashes.SHA256())
	key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
	public_pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
	return key_pem, request.public_bytes(serialization.Encoding.PEM).decode(), public_pem
