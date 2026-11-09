{
	"name": "ERP-VERON Attendance Devices",
	"summary": "Punches of the attendance devices used in Iran (ZKTeco and those like it) into the attendances, "
		"pulled over the network or imported from the file of the device's software",
	"description": """
- Devices: ZKTeco and the many devices sold in Iran on its protocol (Virdi, Hikvision and others export a
  file), with their address, port and password, pulled by a scheduled action or a button. Pulling over the
  network needs the «pyzk» library on the server; without it, the file is imported
- The file of the device's software (Excel or text): the device code of the person and the time, in any of
  the usual layouts; Shamsi dates are read too
- Each punch kept once, the person found by the device code on the employee, and the punches of a day made
  into check-ins and check-outs, in their order; the punches of unknown codes are listed to be matched
- What the devices gave is not changed by hand: a correction is asked as an attendance correction
""",
	"version": "19.0.1.0.0",
	"category": "Human Resources/Attendances",
	"author": "ERP-VERON",
	"license": "LGPL-3",
	"depends": ["hr_attendance", "veron_core"],
	"external_dependencies": {"python": []},
	"data": [
		"security/ir.model.access.csv",
		"data/cron.xml",
		"wizard/import_views.xml",
		"views/device_views.xml",
	],
	"installable": True,
}
