# Odoo trial: start, stop, see the log, update a module you changed, or remove everything.
#
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 start
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 createdb trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 stop
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 logs
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 update veron_base trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 remove

param([string]$Action = "start", [string]$Module = "", [string]$Database = "trial")
Set-Location $PSScriptRoot

switch ($Action) {
	"start" {
		docker compose up -d
		if ($LASTEXITCODE -ne 0) { Write-Host "Could not start; is Docker Desktop running?"; exit 1 }
		Write-Host "Odoo is starting: open http://localhost:8069 in a minute."
	}
	"createdb" {
		# The same as the web page's «Create database», with its progress shown here: in Persian,
		# without demo data, the administrator signing in as admin / admin
		$name = if ($Module) { $Module } else { $Database }
		Write-Host "Creating the database $name (a few minutes; the lines below are its progress)..."
		docker compose up -d db
		docker compose stop odoo
		docker compose run --rm odoo -d $name -i base --load-language=fa_IR --stop-after-init
		$ok = $LASTEXITCODE -eq 0
		docker compose start odoo
		if (-not $ok) { Write-Host "It did not finish; the lines above say why."; exit 1 }
		Write-Host ""
		Write-Host "Database $name is ready. Open http://localhost:8069 and sign in with admin / admin, then change the password."
	}
	"stop" { docker compose stop }
	"logs" { docker compose logs -f --tail 100 odoo }
	"update" {
		if (-not $Module) { Write-Host "Which module? For example: .\odoo.ps1 update veron_base trial"; exit 1 }
		# Python changes need Odoo restarted; the module's data and views are read again with -u
		docker compose stop odoo
		docker compose run --rm odoo -d $Database -u $Module --stop-after-init
		docker compose start odoo
	}
	"remove" {
		$answer = Read-Host "This deletes Odoo, its database and its files (your addons folder stays). Type yes"
		if ($answer -ne "yes") { Write-Host "Nothing was removed."; exit 0 }
		docker compose down -v
		docker image rm odoo:19.0 postgres:16
		Write-Host "Removed. To give the space back to Windows, see README.md (Compact the Docker disk)."
	}
	default { Write-Host "Use: start, createdb [name], stop, logs, update <module> [database], remove" }
}
