# Odoo trial: start, stop, see the log, update a module you changed, or remove everything.
#
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 start
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 createdb trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 stop
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 logs
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 oca
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 install web_responsive trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 update veron_base trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 remove

param([string]$Action = "start", [string]$Module = "", [string]$Database = "trial")
Set-Location $PSScriptRoot

# The OCA repositories of oca-repos.txt, on their 19.0 branch: fetched once, brought up to date after
function Get-Oca {
	New-Item -ItemType Directory -Force -Path oca | Out-Null
	foreach ($line in Get-Content oca-repos.txt) {
		$repo = $line.Trim()
		if (-not $repo -or $repo.StartsWith("#")) { continue }
		if (Test-Path "oca\$repo\.git") {
			Write-Host "     updating $repo"
			git -C "oca\$repo" pull --quiet --ff-only
		} else {
			Write-Host "     fetching $repo"
			git clone --quiet --depth 1 --branch 19.0 "https://github.com/OCA/$repo.git" "oca\$repo"
		}
		if ($LASTEXITCODE -ne 0) { Write-Host "Could not fetch $repo; check the internet connection and try again."; exit 1 }
	}
}

switch ($Action) {
	"oca" {
		Write-Host "Fetching the OCA modules..."
		Get-Oca
		docker compose restart odoo
		Write-Host "Done. Install what you need with: .\odoo.ps1 install <module> <database>"
	}
	"start" {
		# The OCA folders must be there before Odoo starts
		if (-not (Test-Path "oca\web\.git")) { Write-Host "Fetching the OCA modules (first time)..."; Get-Oca }
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
	"install" {
		# A module in the addons folder installed into a database, without the Apps menu
		if (-not $Module) { Write-Host "Which module? For example: .\odoo.ps1 install web_responsive trial"; exit 1 }
		docker compose stop odoo
		docker compose run --rm odoo -d $Database -i $Module --stop-after-init
		$ok = $LASTEXITCODE -eq 0
		docker compose start odoo
		if ($ok) { Write-Host "Installed $Module in $Database. Reload the page in the browser." } else { Write-Host "It did not install; the lines above say why."; exit 1 }
	}
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
	default { Write-Host "Use: start, oca, createdb [name], stop, logs, install <module> [database], update <module> [database], remove" }
}
