# A separate environment for each business: its own site with its own database, at
# http://<name>.localhost:8080 (browsers send every *.localhost address to this computer).
#
#   powershell -ExecutionPolicy Bypass -File .\business.ps1 list
#   powershell -ExecutionPolicy Bypass -File .\business.ps1 new shop
#   powershell -ExecutionPolicy Bypass -File .\business.ps1 open shop      (log in as its Administrator, no password)
#   powershell -ExecutionPolicy Bypass -File .\business.ps1 demo shop      (sample data of its kind of business)
#   powershell -ExecutionPolicy Bypass -File .\business.ps1 reset shop     (delete all and start again)
#   powershell -ExecutionPolicy Bypass -File .\business.ps1 remove shop
#
# The name is the address: small English letters, digits and dashes (shop, car-showroom, cafe2).
# For a business reached from the internet, give its full address instead: shop.example.ir (a
# subdomain of your domain whose DNS points to this server, see nginx/sites.conf).
# The main site at http://localhost:8080 is not touched; reset.ps1 starts that one again.
# The "Customer Systems" panel on the main site lists every business; update.ps1 updates them all.

param(
	[Parameter(Position = 0)][ValidateSet("list", "new", "open", "demo", "reset", "remove")][string]$Action = "list",
	[Parameter(Position = 1)][string]$Name
)

Set-Location $PSScriptRoot

# Passwords and port from .env
$envFile = @{}
Get-Content .env | Where-Object { $_ -match "^\s*[A-Z_]+\s*=" } | ForEach-Object {
	$key, $value = $_ -split "=", 2
	$envFile[$key.Trim()] = $value.Trim()
}
$port = if ($envFile["HTTP_PORT"]) { $envFile["HTTP_PORT"] } else { "8080" }

# Every site but the main one is a business
function Sites {
	docker compose exec -T backend bash -c 'cd sites && for d in */; do d=${d%/}; [ -f $d/site_config.json ] && [ $d != frontend ] && echo $d; done'
}

function Url($site) {
	$suffix = if ($port -eq "80") { "" } else { ":$port" }
	return "http://$($site)$suffix"
}

if ($Action -eq "list") {
	Write-Host "Main site:  $(Url 'localhost')"
	foreach ($site in Sites) { if ($site) { Write-Host "Business:   $(Url $site)" } }
	exit 0
}

if (-not $Name -or $Name -notmatch "^[a-z0-9-]+(\.[a-z0-9-]+)*$") {
	Write-Host "Give the business a name of small English letters, digits and dashes, for example: shop"
	Write-Host "(or its full internet address, for example: shop.example.ir)"
	exit 1
}
# A plain name is a local address; a name with dots is the business's own internet address
$site = if ($Name.Contains(".")) { $Name } else { "$Name.localhost" }
$exists = (Sites) -contains $site

function New-Site {
	$title = Read-Host "Business name (Persian is fine)"
	if (-not $title) { $title = $Name }
	$abbr = ($Name.Split(".")[0] -replace "[^a-z0-9]", "").ToUpper()
	if ($abbr.Length -gt 5) { $abbr = $abbr.Substring(0, 5) }
	Write-Host "Making the site $site (a few minutes)..."
	docker compose exec -T backend bench new-site $site "--mariadb-user-host-login-scope=%" `
		"--admin-password=$($envFile['ADMIN_PASSWORD'])" --db-root-username=root `
		"--db-root-password=$($envFile['DB_ROOT_PASSWORD'])" --install-app erpnext --install-app iran_erp
	if ($LASTEXITCODE -ne 0) { Write-Host "Making the site failed; see above."; exit 1 }
	Write-Host "Setting up (Persian, Iran, rial, Iranian chart of accounts)..."
	docker compose exec -T -e "IRAN_COMPANY=$title" -e "IRAN_ABBR=$abbr" backend `
		bench --site $site execute iran_erp.fresh_start.run
	Write-Host ""
	Write-Host "Ready: $(Url $site)  (Administrator, the ADMIN_PASSWORD of .env)"
	Write-Host "The first login opens Easy Setup: choose the kind of business and what it needs."
}

function Remove-Site {
	docker compose exec -T backend bench drop-site $site --db-root-username=root `
		"--db-root-password=$($envFile['DB_ROOT_PASSWORD'])" --force --no-backup
}

switch ($Action) {
	"new" {
		if ($exists) { Write-Host "$site already exists: $(Url $site)"; exit 1 }
		New-Site
	}
	"open" {
		if (-not $exists) { Write-Host "$site does not exist"; exit 1 }
		# Frappe's own one-time login: a new session of its Administrator, opened in the browser
		$out = docker compose exec -T backend bench --site $site browse --user Administrator 2>&1 | Out-String
		if ($out -notmatch "sid=([0-9a-f]+)") { Write-Host $out; Write-Host "Could not log in."; exit 1 }
		$url = "$(Url $site)/app?sid=$($Matches[1])"
		Write-Host "Opening $site as its Administrator..."
		Start-Process $url
	}
	"demo" {
		if (-not $exists) { Write-Host "$site does not exist; make it first: .\business.ps1 new $Name"; exit 1 }
		Write-Host "Loading the sample data of the business chosen in Easy Setup into $site..."
		docker compose exec -T -e "IRAN_DEMO=1" backend bench --site $site execute iran_erp.fresh_start.run
	}
	"reset" {
		if (-not $exists) { Write-Host "$site does not exist"; exit 1 }
		$answer = Read-Host "ALL data of $site will be deleted and cannot be brought back. Type YES to continue"
		if ($answer -ne "YES") { Write-Host "Nothing was deleted."; exit 1 }
		Remove-Site
		New-Site
	}
	"remove" {
		if (-not $exists) { Write-Host "$site does not exist"; exit 1 }
		$answer = Read-Host "$site and ALL its data will be deleted. Type YES to continue"
		if ($answer -ne "YES") { Write-Host "Nothing was deleted."; exit 1 }
		Remove-Site
		Write-Host "$site was removed."
	}
}
