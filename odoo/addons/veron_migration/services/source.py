"""The old system: a backup of the database manager (zip or folder) and the database it is loaded into, read only"""

import json
import os
import subprocess
import tempfile
import zipfile


def text(value, lang="fa_IR"):
	"""A translated value of Odoo (a JSON of languages) in Persian when it has it, else in English"""
	if isinstance(value, str) and value.startswith("{"):
		try:
			value = json.loads(value)
		except ValueError:
			return value
	if isinstance(value, dict):
		return value.get(lang) or value.get("en_US") or next(iter(value.values()), "") or ""
	return value or ""


class Backup:
	"""The zip of the database manager or its unpacked folder: the manifest, dump.sql and the filestore"""

	def __init__(self, path, filestore=None):
		self.path = path
		self.filestore = filestore
		self.zip = None if not path or os.path.isdir(path) else zipfile.ZipFile(path)

	def manifest(self):
		if self.zip:
			return json.loads(self.zip.read("manifest.json"))
		with open(os.path.join(self.path, "manifest.json"), encoding="utf-8") as handle:
			return json.load(handle)

	def dump(self, folder):
		if not self.zip:
			return os.path.join(self.path, "dump.sql")
		return self.zip.extract("dump.sql", folder)

	def file(self, store_fname):
		"""A file of the filestore; None when the backup was made without it"""
		if self.filestore:
			# An old database already on this server: its files are in its own filestore
			try:
				with open(os.path.join(self.filestore, store_fname), "rb") as handle:
					return handle.read()
			except OSError:
				return None
		if not self.path:
			return None
		name = "filestore/" + store_fname
		try:
			if self.zip:
				return self.zip.read(name)
			with open(os.path.join(self.path, name), "rb") as handle:
				return handle.read()
		except (KeyError, OSError):
			return None


class Old:
	"""The old database, read by SQL: its tables differ from version to version, so every column is looked up"""

	def __init__(self, cr):
		self.cr = cr
		self._columns = {}

	@classmethod
	def connect(cls, dsn):
		import psycopg2
		import psycopg2.extras

		connection = psycopg2.connect(dsn)
		connection.set_session(readonly=True)
		old = cls(connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor))
		old.connection = connection
		return old

	def columns(self, table):
		if table not in self._columns:
			self.cr.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s "
				"AND table_schema = current_schema()", (table,))
			self._columns[table] = {row["column_name"]: row["data_type"] for row in self._dicts()}
		return self._columns[table]

	def has(self, table, column=None):
		columns = self.columns(table)
		return bool(columns) and (column is None or column in columns)

	def _dicts(self):
		rows = self.cr.fetchall()
		if rows and not isinstance(rows[0], dict):
			names = [d[0] for d in self.cr.description]
			rows = [dict(zip(names, row)) for row in rows]
		return rows

	def rows(self, query, params=()):
		self.cr.execute(query, params)
		return self._dicts()

	def value(self, query, params=()):
		rows = self.rows(query, params)
		return next(iter(rows[0].values())) if rows else None


def load(backup, database, reload=False, say=print):
	"""The dump of the backup loaded into a database of its own, once; the connection string to it"""
	import psycopg2

	host, user, password = os.environ.get("HOST", "db"), os.environ.get("USER", "odoo"), os.environ.get("PASSWORD", "odoo")
	admin = psycopg2.connect(host=host, user=user, password=password, dbname="postgres")
	admin.autocommit = True
	with admin.cursor() as cr:
		cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
		exists = bool(cr.fetchone())
		if exists and reload:
			cr.execute(f'DROP DATABASE "{database}"')
			exists = False
		if exists:
			say(f"The old database {database} is already loaded; it is read again (--reload loads it anew).")
		else:
			cr.execute(f"CREATE DATABASE \"{database}\" ENCODING 'UTF8' TEMPLATE template0")
	admin.close()
	if not exists:
		say(f"Loading the backup into {database} (a few minutes for a large company)...")
		with tempfile.TemporaryDirectory() as folder:
			dump = backup.dump(folder)
			result = subprocess.run(["psql", "-h", host, "-U", user, "-d", database, "-q", "-X", "-v", "ON_ERROR_STOP=0",
				"-f", dump], env=dict(os.environ, PGPASSWORD=password), capture_output=True, text=True)
		errors = [line for line in result.stderr.splitlines() if "ERROR" in line and "role" not in line]
		if errors:
			say(f"  {len(errors)} lines of the dump were not loaded; the first: {errors[0][:200]}")
	return f"host={host} user={user} password={password} dbname={database}"
