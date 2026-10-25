# Odoo trial: start, stop, see the log, update a module you changed, or remove everything.
#
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 start
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
	default { Write-Host "Use: start, stop, logs, update <module> [database], remove" }
}
