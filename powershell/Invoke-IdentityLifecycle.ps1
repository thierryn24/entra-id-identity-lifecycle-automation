[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputCsv,

    [Parameter(Mandatory = $true)]
    [string]$PolicyPath,

    [switch]$Apply,

    [switch]$UseDeviceCode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Requires Microsoft.Graph.Authentication. Install once with:
# Install-Module Microsoft.Graph -Scope CurrentUser
Import-Module Microsoft.Graph.Authentication

$GraphRoot = 'https://graph.microsoft.com/v1.0'
$RunId = [guid]::NewGuid().Guid
$AuditDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'logs'
New-Item -ItemType Directory -Path $AuditDirectory -Force | Out-Null
$AuditPath = Join-Path $AuditDirectory ("identity-lifecycle-{0:yyyyMMdd}.jsonl" -f (Get-Date).ToUniversalTime())

function Write-Audit {
    param(
        [Parameter(Mandatory = $true)][string]$Event,
        [hashtable]$Fields = @{}
    )
    $record = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
        run_id    = $RunId
        event     = $Event
    }
    foreach ($key in $Fields.Keys) {
        if ($key -notin @('password', 'secret', 'access_token', 'client_secret')) {
            $record[$key] = $Fields[$key]
        }
    }
    ($record | ConvertTo-Json -Compress -Depth 10) | Add-Content -Path $AuditPath -Encoding UTF8
}

function Invoke-GraphSafe {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('GET', 'POST', 'PATCH', 'DELETE')][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body,
        [int[]]$ExpectedStatusCodes = @(200, 201, 202, 204)
    )
    $attempt = 0
    $maxAttempts = 5
    do {
        try {
            $params = @{
                Method      = $Method
                Uri         = $Uri
                OutputType  = 'PSObject'
                ErrorAction = 'Stop'
            }
            if ($null -ne $Body) {
                $params.BodyParameter = $Body
                $params.ContentType = 'application/json'
            }
            return Invoke-MgGraphRequest @params
        }
        catch {
            $message = $_.Exception.Message
            $retryable = $message -match '429|500|502|503|504|timeout|temporarily'
            if (-not $retryable -or $attempt -ge ($maxAttempts - 1)) { throw }
            Start-Sleep -Seconds ([math]::Min(60, [math]::Pow(2, $attempt) + (Get-Random -Minimum 0 -Maximum 2)))
            $attempt++
        }
    } while ($attempt -lt $maxAttempts)
}

function Get-GraphUser {
    param([Parameter(Mandatory = $true)][string]$Upn)
    $encoded = [uri]::EscapeDataString($Upn)
    try {
        return Invoke-GraphSafe -Method GET -Uri "$GraphRoot/users/$encoded`?`$select=id,userPrincipalName,accountEnabled,assignedLicenses"
    }
    catch {
        if ($_.Exception.Message -match '404') { return $null }
        throw
    }
}

function Get-AllGraphItems {
    param([Parameter(Mandatory = $true)][string]$Uri)
    $items = @()
    $next = $Uri
    while ($next) {
        $page = Invoke-GraphSafe -Method GET -Uri $next
        if ($page.value) { $items += @($page.value) }
        $next = $page.'@odata.nextLink'
    }
    return $items
}

function Get-UserGroupIds {
    param([Parameter(Mandatory = $true)][string]$UserId)
    $items = Get-AllGraphItems -Uri "$GraphRoot/users/$UserId/memberOf/microsoft.graph.group?`$select=id"
    return @($items | ForEach-Object { [string]$_.id })
}

function Ensure-User {
    param(
        [Parameter(Mandatory = $true)]$Worker,
        [Parameter(Mandatory = $true)]$Policy
    )
    $existing = Get-GraphUser -Upn $Worker.upn
    $common = @{
        accountEnabled    = $true
        displayName       = $Worker.display_name
        givenName         = $Worker.first_name
        surname           = $Worker.last_name
        department        = $Worker.department
        jobTitle          = $Worker.job_title
        employeeId        = $Worker.worker_id
        usageLocation     = $Policy.default_usage_location
    }
    if ($existing) {
        Invoke-GraphSafe -Method PATCH -Uri "$GraphRoot/users/$($existing.id)" -Body $common | Out-Null
        return $existing
    }
    if ([string]$Policy.source_of_authority -in @('on_premises_ad', 'hybrid')) {
        throw "Refusing cloud creation for $($Worker.upn): source_of_authority is $($Policy.source_of_authority)."
    }
    $initialPassword = $env:IDENTITY_LIFECYCLE_INITIAL_PASSWORD
    if ([string]::IsNullOrWhiteSpace($initialPassword)) {
        throw 'IDENTITY_LIFECYCLE_INITIAL_PASSWORD must be supplied for a new cloud user; do not put it in source files.'
    }
    $alias = ($Worker.upn -split '@')[0] -replace '[^A-Za-z0-9._-]', ''
    $payload = $common + @{
        mailNickname       = $alias.Substring(0, [math]::Min(64, $alias.Length))
        userPrincipalName  = $Worker.upn
        passwordProfile    = @{
            forceChangePasswordNextSignIn = $true
            password = $initialPassword
        }
    }
    return Invoke-GraphSafe -Method POST -Uri "$GraphRoot/users" -Body $payload -ExpectedStatusCodes @(201)
}

function Get-DesiredGroupIds {
    param(
        [Parameter(Mandatory = $true)]$Worker,
        [Parameter(Mandatory = $true)]$Policy
    )
    $ids = @($Policy.managed_group_ids)
    foreach ($mapping in @($Policy.role_mappings)) {
        if ((-not $mapping.department -or [string]$mapping.department -eq [string]$Worker.department) -and
            (-not $mapping.job_title -or [string]$mapping.job_title -eq [string]$Worker.job_title)) {
            $ids += @($mapping.group_ids)
            $ids += @($mapping.license_group_ids)
        }
    }
    return @($ids | Where-Object { $_ -and $_ -notmatch '^REPLACE_WITH|^\.\.\.$' } | Sort-Object -Unique)
}

function Reconcile-Groups {
    param(
        [Parameter(Mandatory = $true)][string]$UserId,
        [Parameter(Mandatory = $true)][string[]]$DesiredGroupIds,
        [Parameter(Mandatory = $true)]$Policy,
        [Parameter(Mandatory = $true)][string]$WorkerId,
        [Parameter(Mandatory = $true)][string]$Upn
    )
    $managed = @($Policy.managed_group_ids)
    foreach ($mapping in @($Policy.role_mappings)) {
        $managed += @($mapping.group_ids)
        $managed += @($mapping.license_group_ids)
    }
    $managed = @($managed | Where-Object { $_ -and $_ -notmatch '^REPLACE_WITH|^\.\.\.$' } | Sort-Object -Unique)
    $current = @(Get-UserGroupIds -UserId $UserId | Where-Object { $_ -in $managed })
    foreach ($groupId in @($DesiredGroupIds | Where-Object { $_ -notin $current })) {
        Invoke-GraphSafe -Method POST -Uri "$GraphRoot/groups/$groupId/members/`$ref" -Body @{ '@odata.id' = "$GraphRoot/directoryObjects/$UserId" } -ExpectedStatusCodes @(204) | Out-Null
        Write-Audit -Event 'group_member_added' -Fields @{ action = 'reconcile_managed_groups'; worker_id = $WorkerId; upn = $Upn; group_id = $groupId; object_id = $UserId }
    }
    foreach ($groupId in @($current | Where-Object { $_ -notin $DesiredGroupIds })) {
        Invoke-GraphSafe -Method DELETE -Uri "$GraphRoot/groups/$groupId/members/$UserId/`$ref" -ExpectedStatusCodes @(204) | Out-Null
        Write-Audit -Event 'group_member_removed' -Fields @{ action = 'reconcile_managed_groups'; worker_id = $WorkerId; upn = $Upn; group_id = $groupId; object_id = $UserId }
    }
}

function Remove-Termination-Access {
    param(
        [Parameter(Mandatory = $true)][string]$UserId,
        [Parameter(Mandatory = $true)]$Policy,
        [Parameter(Mandatory = $true)][string]$WorkerId,
        [Parameter(Mandatory = $true)][string]$Upn
    )
    Invoke-GraphSafe -Method PATCH -Uri "$GraphRoot/users/$UserId" -Body @{ accountEnabled = $false } | Out-Null
    Write-Audit -Event 'user_disabled' -Fields @{ action = 'disable_user'; worker_id = $WorkerId; upn = $Upn; object_id = $UserId }
    Invoke-GraphSafe -Method POST -Uri "$GraphRoot/users/$UserId/revokeSignInSessions" -ExpectedStatusCodes @(200, 204) | Out-Null
    Write-Audit -Event 'sessions_revoked' -Fields @{ action = 'revoke_sign_in_sessions'; worker_id = $WorkerId; upn = $Upn; object_id = $UserId }

    $managed = @($Policy.managed_group_ids)
    foreach ($mapping in @($Policy.role_mappings)) {
        $managed += @($mapping.group_ids)
        $managed += @($mapping.license_group_ids)
    }
    $managed = @($managed | Where-Object { $_ -and $_ -notmatch '^REPLACE_WITH|^\.\.\.$' } | Sort-Object -Unique)
    foreach ($groupId in @(Get-UserGroupIds -UserId $UserId | Where-Object { $_ -in $managed })) {
        Invoke-GraphSafe -Method DELETE -Uri "$GraphRoot/groups/$groupId/members/$UserId/`$ref" -ExpectedStatusCodes @(204) | Out-Null
        Write-Audit -Event 'termination_group_removed' -Fields @{ action = 'remove_managed_group_memberships'; worker_id = $WorkerId; upn = $Upn; group_id = $groupId; object_id = $UserId }
    }

    if ($Policy.termination.remove_direct_licenses) {
        $states = Get-AllGraphItems -Uri "$GraphRoot/users/$UserId/licenseAssignmentStates?`$select=skuId,assignedByGroup"
        $directSkus = @($states | Where-Object { -not $_.assignedByGroup -and $_.skuId } | ForEach-Object { [string]$_.skuId } | Sort-Object -Unique)
        if ($directSkus.Count -gt 0) {
            Invoke-GraphSafe -Method POST -Uri "$GraphRoot/users/$UserId/assignLicense" -Body @{ addLicenses = @(); removeLicenses = $directSkus } | Out-Null
        }
        Write-Audit -Event 'direct_licenses_removed' -Fields @{ action = 'remove_direct_licenses'; worker_id = $WorkerId; upn = $Upn; sku_ids = $directSkus; object_id = $UserId }
    }
}

$policy = Get-Content -Raw -Path $PolicyPath | ConvertFrom-Json
$workers = @(Import-Csv -Path $InputCsv)
if ($workers.Count -eq 0) { throw 'Worker input is empty.' }
$terminationCount = @($workers | Where-Object { $_.employment_status -in @('Terminated', 'Offboarded', 'Disabled') }).Count
$maxTerminations = [int]$policy.execution.max_terminations_per_run
if ($terminationCount -gt $maxTerminations) { throw "Termination safety limit exceeded: $terminationCount > $maxTerminations" }

$mode = if ($Apply) { 'apply' } else { 'dry_run' }
Write-Audit -Event 'run_started' -Fields @{ mode = $mode; input = $InputCsv; worker_count = $workers.Count }

if ($UseDeviceCode) {
    Connect-MgGraph -TenantId $policy.tenant_id -Scopes @('User.ReadWrite.All', 'GroupMember.ReadWrite.All', 'LicenseAssignment.ReadWrite.All', 'User.RevokeSessions.All') -UseDeviceCode -NoWelcome
}
elseif ($Apply) {
    Connect-MgGraph -Identity -NoWelcome
}

foreach ($worker in $workers) {
    $isTerminated = $worker.employment_status -in @('Terminated', 'Offboarded', 'Disabled')
    if (-not $Apply) {
        if ($isTerminated) {
            Write-Audit -Event 'action_planned' -Fields @{ action = 'disable_user'; worker_id = $worker.worker_id; upn = $worker.upn }
            Write-Audit -Event 'action_planned' -Fields @{ action = 'revoke_sign_in_sessions'; worker_id = $worker.worker_id; upn = $worker.upn }
            Write-Audit -Event 'action_planned' -Fields @{ action = 'remove_managed_group_memberships'; worker_id = $worker.worker_id; upn = $worker.upn }
            Write-Audit -Event 'action_planned' -Fields @{ action = 'remove_direct_licenses'; worker_id = $worker.worker_id; upn = $worker.upn }
        }
        else {
            Write-Audit -Event 'action_planned' -Fields @{ action = 'ensure_user'; worker_id = $worker.worker_id; upn = $worker.upn }
            Write-Audit -Event 'action_planned' -Fields @{ action = 'reconcile_managed_groups'; worker_id = $worker.worker_id; upn = $worker.upn; desired_group_ids = @(Get-DesiredGroupIds -Worker $worker -Policy $policy) }
        }
        continue
    }

    try {
        if ($isTerminated) {
            $user = Get-GraphUser -Upn $worker.upn
            if (-not $user) { Write-Audit -Event 'termination_user_not_found' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn }; continue }
            Remove-Termination-Access -UserId $user.id -Policy $policy -WorkerId $worker.worker_id -Upn $worker.upn
        }
        else {
            $user = Ensure-User -Worker $worker -Policy $policy
            Write-Audit -Event 'user_ensured' -Fields @{ action = 'ensure_user'; worker_id = $worker.worker_id; upn = $worker.upn; object_id = $user.id }
            $desired = @(Get-DesiredGroupIds -Worker $worker -Policy $policy)
            Reconcile-Groups -UserId $user.id -DesiredGroupIds $desired -Policy $policy -WorkerId $worker.worker_id -Upn $worker.upn
        }
    }
    catch {
        Write-Audit -Event 'action_failed' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; error = $_.Exception.Message.Substring(0, [math]::Min(500, $_.Exception.Message.Length)) }
        throw
    }
}

Write-Audit -Event 'run_completed' -Fields @{ mode = $mode; worker_count = $workers.Count; audit_path = $AuditPath }
Write-Output "Mode: $mode"
Write-Output "Audit log: $AuditPath"
