# Odoo trial: start, stop, see the log, update a module you changed, or remove everything.
#
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 start
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 createdb trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 stop
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 logs
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 oca
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 install web_responsive trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 install veron_apps trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 update veron_base trial
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 ai
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 voice
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 restore <backup zip or folder> <database>
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 import18 <backup zip or folder> <database>
#   powershell -ExecutionPolicy Bypass -File .\odoo.ps1 dropdb <database>
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

# Odoo needs every folder of addons_path (web_responsive is in oca\web): the repositories missing are
# fetched before Odoo runs. True when something was fetched, so a running Odoo is restarted to see it.
function Confirm-Oca {
	$missing = Get-Content oca-repos.txt | ForEach-Object { $_.Trim() } |
		Where-Object { $_ -and -not $_.StartsWith("#") -and -not (Test-Path "oca\$_\.git") }
	if (-not $missing) { return $false }
	Write-Host "Fetching the OCA modules missing: $($missing -join ', ')..."
	Get-Oca | Out-Host
	return $true
}

# Odoo is always brought up with «up», never «start» or «restart»: those reuse the container as it was
# first made, without what docker-compose.yml has gained since (the oca folder, for one)
switch ($Action) {
	"oca" {
		Write-Host "Fetching the OCA modules..."
		Get-Oca
		# Created again, not restarted: a container made before oca was mounted would never see it
		docker compose up -d --force-recreate odoo
		Write-Host "Done. Install what you need with: .\odoo.ps1 install <module> <database>"
	}
	"start" {
		$fetched = Confirm-Oca
		# --build: the image with the built-in OCR is made the first time and after its Dockerfile changes
		docker compose up -d --build
		if ($LASTEXITCODE -ne 0) { Write-Host "Could not start; is Docker Desktop running?"; exit 1 }
		if ($fetched) { docker compose restart odoo }
		Write-Host "Odoo is starting: open http://localhost:8069 in a minute."
	}
	"createdb" {
		# The same as the web page's «Create database», with its progress shown here: in Persian,
		# without demo data, the administrator signing in as admin / admin
		$name = if ($Module) { $Module } else { $Database }
		Write-Host "Creating the database $name (a few minutes; the lines below are its progress)..."
		Confirm-Oca | Out-Null
		docker compose up -d db
		docker compose stop odoo
		docker compose run --rm odoo -d $name -i base --load-language=fa_IR --stop-after-init
		$ok = $LASTEXITCODE -eq 0
		docker compose up -d odoo
		if (-not $ok) { Write-Host "It did not finish; the lines above say why."; exit 1 }
		Write-Host ""
		Write-Host "Database $name is ready. Open http://localhost:8069 and sign in with admin / admin, then change the password."
	}
	"stop" { docker compose stop }
	"logs" { docker compose logs -f --tail 100 odoo }
	"install" {
		# A module in the addons folder installed into a database, without the Apps menu
		if (-not $Module) { Write-Host "Which module? For example: .\odoo.ps1 install web_responsive trial"; exit 1 }
		$Module = ($Module.Trim() -replace '\s+', ',')
		Confirm-Oca | Out-Null
		docker compose build odoo
		docker compose stop odoo
		# Our own modules already installed are brought up to date with it (Odoo skips the others):
		# a module installed before a git pull would otherwise keep its old menus and names
		$ours = (Get-ChildItem addons -Directory | Where-Object { Test-Path (Join-Path $_.FullName "__manifest__.py") } | ForEach-Object { $_.Name }) -join ","
		docker compose run --rm odoo -d $Database -i $Module -u $ours --stop-after-init
		$ok = $LASTEXITCODE -eq 0
		docker compose up -d odoo
		if ($ok) { Write-Host "Installed $Module in $Database. Reload the page in the browser." } else { Write-Host "It did not install; the lines above say why."; exit 1 }
	}
	"update" {
		if (-not $Module) { Write-Host "Which module? For example: .\odoo.ps1 update veron_base trial"; exit 1 }
		# "a,b" is an array to PowerShell and arrives here as "a b": given to Odoo as one list again
		$Module = ($Module.Trim() -replace '\s+', ',')
		Confirm-Oca | Out-Null
		# Python changes need Odoo restarted; the module's data and views are read again with -u
		docker compose stop odoo
		docker compose run --rm odoo -d $Database -u $Module --stop-after-init
		docker compose up -d odoo
	}
	"ai" {
		# The Anthropic library the Claude provider (ai_claude_anthropic) uses, fetched into python\sdk
		# with Odoo's own Python, so it fits the container; set PIP_INDEX_URL first to use a mirror
		Write-Host "Fetching the Anthropic library into python\sdk..."
		docker compose run --rm -T -u root -e PIP_INDEX_URL --entrypoint pip odoo install --quiet --upgrade --target /mnt/python/sdk "anthropic>=2.3,<3"
		if ($LASTEXITCODE -ne 0) { Write-Host "It could not be fetched; the lines above say why (is the internet reachable?)."; exit 1 }
		docker compose restart odoo
		Write-Host "Done. In AI Agents, Settings, Providers, open Claude, enter the key and press Check."
	}
	"restore" {
		# A backup of an Odoo database (the zip of the database manager, or its unpacked folder with dump.sql,
		# manifest.json and filestore) into a database of its own:
		#   .\odoo.ps1 restore "C:\Users\me\Downloads\company_2025-11-12" company
		if (-not $Module -or $Database -eq "trial") { Write-Host "Use: .\odoo.ps1 restore <backup zip or folder> <new database name>"; exit 1 }
		$full = (Resolve-Path $Module -ErrorAction SilentlyContinue).Path
		if (-not $full) { Write-Host "Not found: $Module"; exit 1 }
		$parent = Split-Path $full -Parent
		$leaf = Split-Path $full -Leaf
		docker compose up -d db
		docker compose run --rm -T -v "${parent}:/mnt/backup:ro" --entrypoint python3 odoo /mnt/extra-addons/veron_core/scripts/restore_backup.py "/mnt/backup/$leaf" $Database
		if ($LASTEXITCODE -ne 0) { exit 1 }
		docker compose up -d odoo
		Write-Host "To add the Iranian settings and the programs of ERP-VERON to it: .\odoo.ps1 install veron_apps $Database"
	}
	"import18" {
		# A company of Odoo 16, 17 or 18 (Community or Enterprise) brought into a database of this program with its
		# history: contacts, products, accounts, every invoice and entry, payments, orders, stock, files. Nothing is
		# posted or applied: a person confirms it in the program (Settings, Brought From Odoo):
		#   .\odoo.ps1 import18 "C:\Users\me\Downloads\hermagi_2025-11-12.zip" hermagi
		if (-not $Module -or $Database -eq "trial") { Write-Host "Use: .\odoo.ps1 import18 <backup zip or folder> <database>"; exit 1 }
		$full = (Resolve-Path $Module -ErrorAction SilentlyContinue).Path
		if (-not $full) { Write-Host "Not found: $Module"; exit 1 }
		$parent = Split-Path $full -Parent
		$leaf = Split-Path $full -Leaf
		# The program is stopped meanwhile: the parts the old company used are installed into the database
		docker compose up -d db
		docker compose stop odoo
		# Persian as it is, in this window and in the file import18-<database>.txt kept to read again or to send
		$encoding = [Console]::OutputEncoding
		[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
		docker compose run --rm -T -v "${parent}:/mnt/backup:ro" --entrypoint python3 odoo /mnt/extra-addons/veron_migration/scripts/import_odoo.py "/mnt/backup/$leaf" $Database | Tee-Object -Variable output
		$ok = $LASTEXITCODE -eq 0
		[Console]::OutputEncoding = $encoding
		$log = Join-Path $PSScriptRoot "import18-$Database.txt"
		if ($output) { [System.IO.File]::WriteAllLines($log, [string[]]$output, (New-Object System.Text.UTF8Encoding $true)) }
		docker compose up -d odoo
		Write-Host "The output is kept in $log"
		if (-not $ok) { exit 1 }
	}
	"dropdb" {
		# A database deleted with its files, to start it again:  .\odoo.ps1 dropdb hermagi
		if (-not $Module) { Write-Host "Use: .\odoo.ps1 dropdb <database>"; exit 1 }
		$answer = Read-Host "This deletes the database $Module and everything in it. Type its name to confirm"
		if ($answer -ne $Module) { Write-Host "Nothing was deleted."; exit 0 }
		docker compose up -d db
		docker compose stop odoo
		docker compose run --rm -T --entrypoint sh odoo -c 'odoo db -c /etc/odoo/odoo.conf --db_host $HOST -r $USER -w $PASSWORD drop $0' $Module
		$ok = $LASTEXITCODE -eq 0
		docker compose up -d odoo
		if ($ok) { Write-Host "Deleted: $Module" } else { Write-Host "It was not deleted; the lines above say why."; exit 1 }
	}
	"voice" {
		# The Persian model of Vosk, for voice messages turned into text on the server without any AI; kept in
		# python\voice\fa (not in git). Set VOSK_MODEL_URL first to fetch the zip from a mirror
		Write-Host "Fetching the Persian voice model (about 50 MB)..."
		docker compose run --rm -T -u root -e VOSK_MODEL_URL --entrypoint python3 odoo /mnt/extra-addons/veron_ai_agent/scripts/fetch_voice_model.py
		if ($LASTEXITCODE -ne 0) { Write-Host "It could not be fetched; the lines above say why."; exit 1 }
		docker compose up -d odoo
		Write-Host "Done. Voice messages are now turned into text on the server."
	}
	"remove" {
		$answer = Read-Host "This deletes Odoo, its database and its files (your addons folder stays). Type yes"
		if ($answer -ne "yes") { Write-Host "Nothing was removed."; exit 0 }
		docker compose down -v
		docker image rm veron-odoo:19.0 odoo:19.0 postgres:16
		Write-Host "Removed. To give the space back to Windows, see README.md (Compact the Docker disk)."
	}
	default { Write-Host "Use: start, oca, createdb [name], stop, logs, install <module> [database], update <module> [database], ai, voice, restore <backup> <database>, import18 <backup> <database>, dropdb <database>, remove" }
}
