"""A dBase III file, as the Social Security Organization's program reads its disks: text fields left-aligned,
numbers right-aligned, the records after a header that lists the fields"""

import datetime
import struct

# Windows-1256 has the Arabic «ي» where Persian writes «ی», and no Persian digits: written as Windows does
TO_1256 = str.maketrans({"ی": "ي", "ۀ": "ه", "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6",
	"۷": "7", "۸": "8", "۹": "9", "\u200c": " "})


def write(fields, records, encoding="cp1256"):
	"""`fields`: (name, type C or N, length); `records`: dicts by field name. Returns the bytes of the file"""
	today = datetime.date.today()
	header_size = 32 + 32 * len(fields) + 1
	record_size = 1 + sum(length for _name, _kind, length in fields)
	out = bytearray(struct.pack("<BBBBIHH20x", 0x03, today.year - 1900, today.month, today.day, len(records),
		header_size, record_size))
	for name, kind, length in fields:
		out += struct.pack("<11sc4xBB14x", name.encode("ascii"), kind.encode("ascii"), length, 0)
	out += b"\r"
	for record in records:
		out += b" "
		for name, kind, length in fields:
			value = record.get(name)
			if kind == "N":
				text = str(int(round(value or 0))).encode("ascii")
				if len(text) > length:
					raise ValueError(f"{name}: {value} does not fit in {length} digits")
				out += text.rjust(length)
			else:
				text = str(value or "").translate(TO_1256).encode(encoding, "replace")[:length]
				out += text.ljust(length)
	out += b"\x1a"
	return bytes(out)


def read(data, encoding="cp1256"):
	"""The records of a file written by `write`, for checking it"""
	count, header_size, record_size = struct.unpack("<IHH", data[4:12])
	fields, offset = [], 32
	while data[offset] != 0x0D:
		name = data[offset:offset + 11].split(b"\0")[0].decode("ascii")
		fields.append((name, chr(data[offset + 11]), data[offset + 16]))
		offset += 32
	records, position = [], header_size
	for _index in range(count):
		row, cursor = {}, position + 1
		for name, kind, length in fields:
			raw = data[cursor:cursor + length]
			row[name] = int(raw.strip() or 0) if kind == "N" else raw.decode(encoding).rstrip().replace("ي", "ی")
			cursor += length
		records.append(row)
		position += record_size
	return fields, records
