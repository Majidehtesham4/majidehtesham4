from odoo import models

from . import jalali


class VeronShamsi(models.AbstractModel):
	"""The database function veron_shamsi_start(granularity, date): the first day of the Shamsi month,
	season or year of a date, from a table of the months of 1300 to 1500."""

	_name = "veron.shamsi"
	_description = "Shamsi calendar in the database"

	def init(self):
		cr = self.env.cr
		cr.execute("""
			CREATE TABLE IF NOT EXISTS veron_shamsi_month (
				start date PRIMARY KEY, jy integer NOT NULL, jm integer NOT NULL
			)
		""")
		cr.execute("SELECT count(*) FROM veron_shamsi_month")
		if not cr.fetchone()[0]:
			rows = [(jalali.to_gregorian(jy, jm, 1), jy, jm) for jy in range(1300, 1501) for jm in range(1, 13)]
			cr.executemany("INSERT INTO veron_shamsi_month (start, jy, jm) VALUES (%s, %s, %s)", rows)
		cr.execute("""
			CREATE OR REPLACE FUNCTION veron_shamsi_start(granularity text, day date) RETURNS date AS $$
				SELECT start FROM veron_shamsi_month
				WHERE start <= day AND (
					granularity = 'month'
					OR (granularity = 'quarter' AND jm IN (1, 4, 7, 10))
					OR (granularity = 'year' AND jm = 1)
				)
				ORDER BY start DESC LIMIT 1
			$$ LANGUAGE sql STABLE
		""")
