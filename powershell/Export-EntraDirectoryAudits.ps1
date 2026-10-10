[CmdletBinding()]
param(
    [int]$SinceHours = 24,
    [string]$OutFile = (Join-Path $PSScriptRoot ("..\logs\entra-directory-audit-{0:yyyyMMddHHmmss}.jsonl" -f (Get-Date).ToUniversalTime())),
    [switch]$UseDeviceCode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.Graph.Authentication
$GraphRoot = 'https://graph.microsoft.com/v1.0'
New-Item -ItemType Directory -Path (Split-Path -Parent $OutFile) -Force | Out-Null

if ($UseDeviceCode) {
    Connect-MgGraph -Scopes @('AuditLog.Read.All') -UseDeviceCode -NoWelcome
}
else {
    Connect-MgGraph -Identity -NoWelcome
}

$since = (Get-Date).ToUniversalTime().AddHours(-1 * $SinceHours).ToString('o')
$filter = [uri]::EscapeDataString("activityDateTime ge $since")
$next = "$GraphRoot/auditLogs/directoryAudits?`$filter=$filter&`$orderby=activityDateTime asc"
$count = 0
while ($next) {
    $page = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
    foreach ($item in @($page.value)) {
        # This export intentionally preserves tenant audit fields but emits one JSON object per line.
        ($item | ConvertTo-Json -Compress -Depth 30) | Add-Content -Path $OutFile -Encoding UTF8
        $count++
    }
    $next = $page.'@odata.nextLink'
}
Write-Output "Exported $count directory audit events to $OutFile"
