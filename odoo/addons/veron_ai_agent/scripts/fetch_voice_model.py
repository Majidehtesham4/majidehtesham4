"""Fetches the Persian model of Vosk once, for speech to text on the server without any AI.

Run inside the program's container (odoo.ps1 voice, or ./veron voice on a server). The model is kept in
python/voice/fa, next to the program, and is not in git. VOSK_MODEL_URL may name another address of the zip
(a mirror) when the site of Vosk is not reachable."""

import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

TARGET = os.environ.get("VERON_VOSK_MODEL") or "/mnt/python/voice/fa"
SITE = "https://alphacephei.com/vosk/models/"
NAMES = ("vosk-model-small-fa-0.42", "vosk-model-small-fa-0.5", "vosk-model-small-fa-0.4")


def installed():
	return os.path.isdir(os.path.join(TARGET, "am")) or os.path.isfile(os.path.join(TARGET, "conf", "model.conf"))


def fetch(url, folder):
	print("Fetching " + url)
	path = os.path.join(folder, "model.zip")
	with urllib.request.urlopen(url, timeout=120) as response, open(path, "wb") as handle:
		shutil.copyfileobj(response, handle)
	with zipfile.ZipFile(path) as archive:
		archive.extractall(folder)
	inner = [os.path.join(folder, name) for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))]
	if len(inner) != 1:
		raise ValueError("the zip does not hold one model folder")
	if os.path.isdir(TARGET):
		shutil.rmtree(TARGET)
	os.makedirs(os.path.dirname(TARGET), exist_ok=True)
	shutil.move(inner[0], TARGET)


def main():
	if installed() and "--again" not in sys.argv:
		print("The Persian voice model is already in " + TARGET)
		return 0
	urls = [os.environ["VOSK_MODEL_URL"]] if os.environ.get("VOSK_MODEL_URL") else [SITE + name + ".zip" for name in NAMES]
	for url in urls:
		with tempfile.TemporaryDirectory() as folder:
			try:
				fetch(url, folder)
			except Exception as error:  # noqa: BLE001 - the next address is tried
				print("  not fetched: %s" % error)
				continue
		if installed():
			os.system("chmod -R a+rX " + TARGET)
			print("Done: the Persian voice model is in " + TARGET)
			return 0
	print("The model could not be fetched. Download a Persian model of Vosk (vosk-model-small-fa) by hand, unzip it "
		"into python/voice/fa, or set VOSK_MODEL_URL to the address of its zip and run this again.")
	return 1


if __name__ == "__main__":
	sys.exit(main())
