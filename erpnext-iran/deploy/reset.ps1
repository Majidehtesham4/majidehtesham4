# Start from zero: deletes ALL data of this installation (database, files, site) and makes a
# fresh site with the Iranian setup and the car dealership's sample data.
#
#   cd D:\majidehtesham4\erpnext-iran\deploy
#   powershell -ExecutionPolicy Bypass -File .\reset.ps1
#
# Build the image first if the code changed:  cd ..; docker build -t iran-erp:latest .; cd deploy

Set-Location $PSScriptRoot

$answer = Read-Host "ALL data will be deleted and cannot be brought back. Type YES to continue"
if ($answer -ne "YES") { Write-Host "Nothing was deleted."; exit 1 }

# The compose project's name (the folder's name, unless .env sets COMPOSE_PROJECT_NAME)
$project = (docker compose config --format json | ConvertFrom-Json).name
Write-Host "Project: $project"

Write-Host "Stopping and removing the containers and their volumes..."
docker compose down -v --remove-orphans

# Containers of this project that are still there (started another way) hold its volumes
$left = docker ps -aq --filter "label=com.docker.compose.project=$project"
if ($left) { docker rm -f $left | Out-Null }

# Volumes that survived (in use at the time of «down»)
$volumes = docker volume ls -q --filter "label=com.docker.compose.project=$project"
foreach ($v in $volumes) { docker volume rm -f $v | Out-Null }
$volumes = docker volume ls -q --filter "label=com.docker.compose.project=$project"
if ($volumes) {
	Write-Host "These volumes could not be deleted; close Docker Desktop's other uses of them and run again:"
	$volumes
	exit 1
}
Write-Host "All data deleted."

Write-Host "Starting a fresh site (a few minutes)..."
docker compose up -d
docker compose logs -f create-site
$created = docker compose ps -a --format json create-site | ConvertFrom-Json
if ($created.ExitCode -ne 0) {
	Write-Host "Making the site failed; see the log above."
	exit 1
}

Write-Host "Setting up (Persian, Iran, rial, Iranian chart of accounts) and loading the sample data..."
docker compose exec backend bench --site frontend execute iran_erp.fresh_start.run
Write-Host "Done. Open the system in the browser, press Ctrl+Shift+R and log in as Administrator."
