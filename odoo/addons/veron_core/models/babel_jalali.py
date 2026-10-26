"""Dates formatted by babel in Persian come out in Shamsi: printed reports, emails, the server's group
labels. babel formats each field of a pattern through DateTimeFormat; the date fields are replaced."""

import babel.dates

from . import jalali

_getitem = babel.dates.DateTimeFormat.__getitem__


def __getitem__(self, name):
	if self.locale.language == "fa" and name[0] in "yMLdQD" and hasattr(self.value, "year"):
		return jalali.format_pattern(self.value, name, lambda field: _getitem(self, field))
	return _getitem(self, name)


babel.dates.DateTimeFormat.__getitem__ = __getitem__
