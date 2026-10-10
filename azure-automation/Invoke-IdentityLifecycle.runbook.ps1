<################################################################################
Project 1 — Azure Automation runbook

Runtime: PowerShell 7.4. Import Microsoft.Graph.Authentication.
Authentication: system-assigned or user-assigned managed identity.
Inputs: Automation variables containing the worker CSV and policy JSON, or direct
string parameters for a small pilot. Apply is false by default.

The runbook writes JSON events to job output. Stream Automation job output to
Log Analytics or an approved SIEM for durable retention and alerting.
################################################################################>
[CmdletBinding()]
param(
    [bool]$Apply = $false,
    [string]$WorkerCsv = '',
    [string]$PolicyJson = '',
    [string]$WorkersVariableName = 'IdentityLifecycle-WorkersCsv',
    [string]$PolicyVariableName = 'IdentityLifecycle-PolicyJson',
    [string]$PasswordCredentialName = 'IdentityLifecycle-InitialPassword',
    [string]$UserAssignedManagedIdentityClientId = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.Graph.Authentication

$GraphRoot = 'https://graph.microsoft.com/v1.0'
$RunId = [guid]::NewGuid().Guid

function Write-Audit {
    param([Parameter(Mandatory = $true)][string]$Event, [hashtable]$Fields = @{})
    $record = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
        run_id = $RunId
        event = $Event
    }
    foreach ($key in $Fields.Keys) {
        if ($key -notin @('password', 'secret', 'access_token', 'client_secret')) { $record[$key] = $Fields[$key] }
    }
    Write-Output ($record | ConvertTo-Json -Compress -Depth 10)
}

function Invoke-GraphWithRetry {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('GET', 'POST', 'PATCH', 'DELETE')][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body
    )
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            $params = @{ Method = $Method; Uri = $Uri; OutputType = 'PSObject'; ErrorAction = 'Stop' }
            if ($null -ne $Body) { $params.BodyParameter = $Body; $params.ContentType = 'application/json' }
            return Invoke-MgGraphRequest @params
        }
        catch {
            if ($attempt -ge 4 -or $_.Exception.Message -notmatch '429|500|502|503|504|timeout|temporarily') { throw }
            Start-Sleep -Seconds ([math]::Min(60, [math]::Pow(2, $attempt) + (Get-Random -Minimum 0 -Maximum 2)))
        }
    }
}

function Get-AllItems {
    param([Parameter(Mandatory = $true)][string]$Uri)
    $items = @(); $next = $Uri
    while ($next) {
        $page = Invoke-GraphWithRetry -Method GET -Uri $next
        if ($page.value) { $items += @($page.value) }
        $next = $page.'@odata.nextLink'
    }
    return $items
}

function Get-User {
    param([Parameter(Mandatory = $true)][string]$Upn)
    try {
        $encoded = [uri]::EscapeDataString($Upn)
        return Invoke-GraphWithRetry -Method GET -Uri "$GraphRoot/users/$encoded`?`$select=id,userPrincipalName,accountEnabled"
    }
    catch {
        if ($_.Exception.Message -match '404') { return $null }
        throw
    }
}

function Get-GroupIds {
    param([Parameter(Mandatory = $true)][string]$UserId)
    return @((Get-AllItems -Uri "$GraphRoot/users/$UserId/memberOf/microsoft.graph.group?`$select=id") | ForEach-Object { [string]$_.id })
}

function Get-ManagedGroupIds {
    param([Parameter(Mandatory = $true)]$Policy)
    $ids = @($Policy.managed_group_ids)
    foreach ($mapping in @($Policy.role_mappings)) {
        $ids += @($mapping.group_ids)
        $ids += @($mapping.license_group_ids)
    }
    return @($ids | Where-Object { $_ -and $_ -notmatch '^REPLACE_WITH|^\.\.\.$' } | Sort-Object -Unique)
}

function Get-DesiredGroupIds {
    param([Parameter(Mandatory = $true)]$Worker, [Parameter(Mandatory = $true)]$Policy)
    $ids = @($Policy.managed_group_ids)
    foreach ($mapping in @($Policy.role_mappings)) {
        if ((-not $mapping.department -or [string]$mapping.department -eq [string]$Worker.department) -and
            (-not $mapping.job_title -or [string]$mapping.job_title -eq [string]$Worker.job_title)) {
            $ids += @($mapping.group_ids); $ids += @($mapping.license_group_ids)
        }
    }
    return @($ids | Where-Object { $_ -and $_ -notmatch '^REPLACE_WITH|^\.\.\.$' } | Sort-Object -Unique)
}

function Ensure-User {
    param([Parameter(Mandatory = $true)]$Worker, [Parameter(Mandatory = $true)]$Policy)
    $existing = Get-User -Upn $Worker.upn
    $common = @{
        accountEnabled = $true; displayName = $Worker.display_name; givenName = $Worker.first_name
        surname = $Worker.last_name; department = $Worker.department; jobTitle = $Worker.job_title
        employeeId = $Worker.worker_id; usageLocation = $Policy.default_usage_location
    }
    if ($existing) {
        Invoke-GraphWithRetry -Method PATCH -Uri "$GraphRoot/users/$($existing.id)" -Body $common | Out-Null
        return $existing
    }
    if ([string]$Policy.source_of_authority -in @('on_premises_ad', 'hybrid')) {
        throw "Refusing cloud creation for $($Worker.upn): source_of_authority is $($Policy.source_of_authority)."
    }
    $credential = Get-AutomationPSCredential -Name $PasswordCredentialName
    if (-not $credential) { throw "Automation credential asset '$PasswordCredentialName' is required for first-time cloud user creation." }
    $alias = (($Worker.upn -split '@')[0] -replace '[^A-Za-z0-9._-]', '')
    $payload = $common + @{
        mailNickname = $alias.Substring(0, [math]::Min(64, $alias.Length))
        userPrincipalName = $Worker.upn
        passwordProfile = @{ forceChangePasswordNextSignIn = $true; password = $credential.GetNetworkCredential().Password }
    }
    return Invoke-GraphWithRetry -Method POST -Uri "$GraphRoot/users" -Body $payload
}

$workerText = if ($WorkerCsv) { $WorkerCsv } else { Get-AutomationVariable -Name $WorkersVariableName }
$policyText = if ($PolicyJson) { $PolicyJson } else { Get-AutomationVariable -Name $PolicyVariableName }
if ([string]::IsNullOrWhiteSpace($workerText) -or [string]::IsNullOrWhiteSpace($policyText)) {
    throw 'WorkerCsv/PolicyJson parameters or the corresponding Automation variables are required.'
}
$policy = $policyText | ConvertFrom-Json
$workers = @($workerText | ConvertFrom-Csv)
if ($workers.Count -eq 0) { throw 'Worker feed is empty.' }
$terminationCount = @($workers | Where-Object { $_.employment_status -in @('Terminated', 'Offboarded', 'Disabled') }).Count
if ($terminationCount -gt [int]$policy.execution.max_terminations_per_run) {
    throw "Termination safety limit exceeded: $terminationCount > $($policy.execution.max_terminations_per_run)"
}

if ($UserAssignedManagedIdentityClientId) {
    Connect-MgGraph -Identity -ClientId $UserAssignedManagedIdentityClientId -NoWelcome
}
else {
    Connect-MgGraph -Identity -NoWelcome
}
Write-Audit -Event 'run_started' -Fields @{ mode = if ($Apply) { 'apply' } else { 'dry_run' }; worker_count = $workers.Count }

foreach ($worker in $workers) {
    $isTerminated = $worker.employment_status -in @('Terminated', 'Offboarded', 'Disabled')
    if (-not $Apply) {
        if ($isTerminated) {
            foreach ($action in @('disable_user', 'revoke_sign_in_sessions', 'remove_managed_group_memberships', 'remove_direct_licenses')) {
                Write-Audit -Event 'action_planned' -Fields @{ action = $action; worker_id = $worker.worker_id; upn = $worker.upn }
            }
        }
        else {
            Write-Audit -Event 'action_planned' -Fields @{ action = 'ensure_user'; worker_id = $worker.worker_id; upn = $worker.upn }
            Write-Audit -Event 'action_planned' -Fields @{ action = 'reconcile_managed_groups'; worker_id = $worker.worker_id; upn = $worker.upn; desired_group_ids = @(Get-DesiredGroupIds -Worker $worker -Policy $policy) }
        }
        continue
    }

    try {
        $user = Get-User -Upn $worker.upn
        if ($isTerminated) {
            if (-not $user) { Write-Audit -Event 'termination_user_not_found' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn }; continue }
            Invoke-GraphWithRetry -Method PATCH -Uri "$GraphRoot/users/$($user.id)" -Body @{ accountEnabled = $false } | Out-Null
            Write-Audit -Event 'user_disabled' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; object_id = $user.id }
            Invoke-GraphWithRetry -Method POST -Uri "$GraphRoot/users/$($user.id)/revokeSignInSessions" | Out-Null
            Write-Audit -Event 'sessions_revoked' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; object_id = $user.id }
            $managed = Get-ManagedGroupIds -Policy $policy
            foreach ($groupId in @(Get-GroupIds -UserId $user.id | Where-Object { $_ -in $managed })) {
                Invoke-GraphWithRetry -Method DELETE -Uri "$GraphRoot/groups/$groupId/members/$($user.id)/`$ref" | Out-Null
                Write-Audit -Event 'termination_group_removed' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; group_id = $groupId; object_id = $user.id }
            }
            continue
        }

        $user = Ensure-User -Worker $worker -Policy $policy
        Write-Audit -Event 'user_ensured' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; object_id = $user.id }
        $desired = @(Get-DesiredGroupIds -Worker $worker -Policy $policy)
        $managed = @(Get-ManagedGroupIds -Policy $policy)
        $current = @(Get-GroupIds -UserId $user.id | Where-Object { $_ -in $managed })
        foreach ($groupId in @($desired | Where-Object { $_ -notin $current })) {
            Invoke-GraphWithRetry -Method POST -Uri "$GraphRoot/groups/$groupId/members/`$ref" -Body @{ '@odata.id' = "$GraphRoot/directoryObjects/$($user.id)" } | Out-Null
            Write-Audit -Event 'group_member_added' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; group_id = $groupId; object_id = $user.id }
        }
        foreach ($groupId in @($current | Where-Object { $_ -notin $desired })) {
            Invoke-GraphWithRetry -Method DELETE -Uri "$GraphRoot/groups/$groupId/members/$($user.id)/`$ref" | Out-Null
            Write-Audit -Event 'group_member_removed' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; group_id = $groupId; object_id = $user.id }
        }
    }
    catch {
        Write-Audit -Event 'action_failed' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; error = $_.Exception.Message.Substring(0, [math]::Min(500, $_.Exception.Message.Length)) }
        throw
    }
}
Write-Audit -Event 'run_completed' -Fields @{ mode = if ($Apply) { 'apply' } else { 'dry_run' }; worker_count = $workers.Count }
