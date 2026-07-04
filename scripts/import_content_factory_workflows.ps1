$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$n8nBaseUrl = if ($env:N8N_BASE_URL) { $env:N8N_BASE_URL.TrimEnd("/") } else { "http://127.0.0.1:5678" }
$email = if ($env:CONTENT_FACTORY_N8N_EMAIL) { $env:CONTENT_FACTORY_N8N_EMAIL } else { "content.factory.local@example.com" }
$password = if ($env:CONTENT_FACTORY_N8N_PASSWORD) { $env:CONTENT_FACTORY_N8N_PASSWORD } else { "ContentFactoryLocal123!" }

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$loginBody = @{
    emailOrLdapLoginId = $email
    password = $password
} | ConvertTo-Json

Invoke-WebRequest `
    -Uri "$n8nBaseUrl/rest/login" `
    -Method Post `
    -ContentType "application/json" `
    -Body $loginBody `
    -WebSession $session `
    -UseBasicParsing `
    -TimeoutSec 30 | Out-Null

$scopes = Invoke-RestMethod `
    -Uri "$n8nBaseUrl/rest/api-keys/scopes" `
    -WebSession $session `
    -TimeoutSec 30

$keyBody = @{
    label = "content-factory-import-$(Get-Date -Format yyyyMMddHHmmss)"
    scopes = $scopes.data
    expiresAt = $null
} | ConvertTo-Json -Depth 8

$keyResponse = Invoke-RestMethod `
    -Uri "$n8nBaseUrl/rest/api-keys" `
    -Method Post `
    -ContentType "application/json" `
    -Body $keyBody `
    -WebSession $session `
    -TimeoutSec 30

$headers = @{
    "X-N8N-API-KEY" = $keyResponse.data.rawApiKey
    "Content-Type" = "application/json"
}

Get-ChildItem workflows\n8n\*.json | Sort-Object Name | ForEach-Object {
    $workflow = Get-Content -Raw $_.FullName | ConvertFrom-Json
    $payload = [ordered]@{
        name = $workflow.name
        nodes = $workflow.nodes
        connections = $workflow.connections
        settings = $workflow.settings
    } | ConvertTo-Json -Depth 100

    $created = Invoke-RestMethod `
        -Uri "$n8nBaseUrl/api/v1/workflows" `
        -Method Post `
        -Headers $headers `
        -Body $payload `
        -TimeoutSec 30

    "Imported $($_.Name): $($created.id) $($created.name)"
}
