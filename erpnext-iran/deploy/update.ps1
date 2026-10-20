# Update everything in one go: gets the new version from GitHub, builds it, restarts the containers
# and brings the main site and every business up to it. Customers are not asked anything; their
# systems are updated here, centrally.
#
#   cd D:\majidehtesham4\erpnext-iran\deploy
#   powershell -ExecutionPolicy Bypass -File .\update.ps1
#
# The "Customer Systems" panel on the main site then shows every business as up to date (or which
# one failed, with its error, and a button to try that one again).

Set-Location $PSScriptRoot

Write-Host "1/4  Getting the new version..."
git -C .. pull
if ($LASTEXITCODE -ne 0) { Write-Host "git pull failed; see above. Nothing was changed."; exit 1 }

Write-Host "2/4  Building (a few minutes)..."
docker build -t iran-erp:latest ..
if ($LASTEXITCODE -ne 0) { Write-Host "The build failed; see above. The running system was not changed."; exit 1 }

# The showroom's website, when it runs here (COMPOSE_PROFILES=website in .env)
if ((Get-Content .env -ErrorAction SilentlyContinue) -match "^\s*COMPOSE_PROFILES\s*=.*website") {
	Write-Host "     and the showroom's website..."
	docker compose build website
	if ($LASTEXITCODE -ne 0) { Write-Host "The website did not build (see above); the system itself is updated." }
}

Write-Host "3/4  Restarting with the new version..."
docker compose up -d
# Wait until the backend answers
for ($i = 0; $i -lt 60; $i++) {
	docker compose exec -T backend bench --version 2>$null | Out-Null
	if ($LASTEXITCODE -eq 0) { break }
	Start-Sleep -Seconds 2
}

Write-Host "4/4  Updating the main site and every business..."
$failed = @()
$sites = docker compose exec -T backend bash -c 'cd sites && for d in */; do d=${d%/}; [ -f $d/site_config.json ] && echo $d; done'
foreach ($site in $sites) {
	if (-not $site) { continue }
	Write-Host "     $site"
	docker compose exec -T backend bench --site $site migrate
	if ($LASTEXITCODE -ne 0) { $failed += $site }
}
docker compose restart frontend queue-short queue-long scheduler websocket | Out-Null

Write-Host ""
if ($failed.Count) {
	Write-Host "Updated, except: $($failed -join ', ')"
	Write-Host "Try those again from the Customer Systems panel, or: docker compose exec backend bench --site <name> migrate"
	exit 1
}
Write-Host "Done: every business is on the new version."
