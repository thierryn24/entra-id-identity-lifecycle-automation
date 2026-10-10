[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputCsv,
    [Parameter(Mandatory = $true)][string]$PolicyPath,
    [Parameter(Mandatory = $true)][string]$TargetOu,
    [switch]$Apply,
    [switch]$EnableAfterCreation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory

$RunId = [guid]::NewGuid().Guid
$AuditPath = Join-Path $PSScriptRoot ("..\logs\ad-joiner-{0:yyyyMMdd}.jsonl")
New-Item -ItemType Directory -Path (Split-Path -Parent $AuditPath) -Force | Out-Null

function Write-Audit {
    param([string]$Event, [hashtable]$Fields = @{})
    $record = [ordered]@{ timestamp = (Get-Date).ToUniversalTime().ToString('o'); run_id = $RunId; event = $Event }
    foreach ($key in $Fields.Keys) { if ($key -notin @('password', 'secret')) { $record[$key] = $Fields[$key] } }
    ($record | ConvertTo-Json -Compress -Depth 10) | Add-Content -Path $AuditPath -Encoding UTF8
}

$policy = Get-Content -Raw -Path $PolicyPath | ConvertFrom-Json
$workers = @(Import-Csv -Path $InputCsv)
if ($workers.Count -eq 0) { throw 'Worker input is empty.' }
$mode = if ($Apply) { 'apply' } else { 'dry_run' }
Write-Audit -Event 'run_started' -Fields @{ mode = $mode; worker_count = $workers.Count; target_ou = $TargetOu }

$password = $env:IDENTITY_LIFECYCLE_INITIAL_PASSWORD
$securePassword = if ($password) { ConvertTo-SecureString -String $password -AsPlainText -Force } else { $null }

foreach ($worker in $workers) {
    $sam = (($worker.upn -split '@')[0] -replace '[^A-Za-z0-9._-]', '').Substring(0, [math]::Min(20, (($worker.upn -split '@')[0] -replace '[^A-Za-z0-9._-]').Length))
    $existing = Get-ADUser -LDAPFilter "(&(objectCategory=person)(userPrincipalName=$($worker.upn)))" -Properties DistinguishedName,Enabled -ErrorAction SilentlyContinue
    $status = [string]$worker.employment_status
    $isTerminated = $status -in @('Terminated', 'Offboarded', 'Disabled')
    if (-not $Apply) {
        Write-Audit -Event 'action_planned' -Fields @{ action = if ($isTerminated) { 'disable_ad_user' } elseif ($existing) { 'update_ad_user' } else { 'create_ad_user' }; worker_id = $worker.worker_id; upn = $worker.upn }
        continue
    }
    try {
        if (-not $existing) {
            if (-not $securePassword) { throw 'IDENTITY_LIFECYCLE_INITIAL_PASSWORD is required to create a new AD user.' }
            New-ADUser -Name $worker.display_name -GivenName $worker.first_name -Surname $worker.last_name `
                -SamAccountName $sam -UserPrincipalName $worker.upn -Path $TargetOu `
                -Department $worker.department -Title $worker.job_title -EmployeeID $worker.worker_id `
                -AccountPassword $securePassword -ChangePasswordAtLogon $true -Enabled:$EnableAfterCreation
            Write-Audit -Event 'ad_user_created' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; sam_account_name = $sam }
            $existing = Get-ADUser -Identity $sam
        }
        else {
            Set-ADUser -Identity $existing.DistinguishedName -Department $worker.department -Title $worker.job_title -EmployeeID $worker.worker_id -DisplayName $worker.display_name
            Write-Audit -Event 'ad_user_updated' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; sam_account_name = $sam }
        }

        $desiredAdGroups = @()
        foreach ($mapping in @($policy.role_mappings)) {
            $departmentMatch = (-not $mapping.department -or [string]$mapping.department -eq [string]$worker.department)
            $titleMatch = (-not $mapping.job_title -or [string]$mapping.job_title -eq [string]$worker.job_title)
            if ($departmentMatch -and $titleMatch) {
                $desiredAdGroups += @($mapping.ad_group_dns)
                if (-not $isTerminated) {
                    foreach ($groupDn in @($mapping.ad_group_dns)) {
                        Add-ADGroupMember -Identity $groupDn -Members $sam -ErrorAction Stop
                        Write-Audit -Event 'ad_group_member_added' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; group_dn = $groupDn }
                    }
                }
            }
        }
        if (-not $isTerminated) {
            $managedAdGroups = @()
            foreach ($mapping in @($policy.role_mappings)) { $managedAdGroups += @($mapping.ad_group_dns) }
            $currentAdGroups = @(Get-ADPrincipalGroupMembership -Identity $sam | ForEach-Object { [string]$_.DistinguishedName })
            foreach ($groupDn in @($currentAdGroups | Where-Object { $_ -in $managedAdGroups -and $_ -notin $desiredAdGroups } | Sort-Object -Unique)) {
                Remove-ADGroupMember -Identity $groupDn -Members $sam -Confirm:$false -ErrorAction Stop
                Write-Audit -Event 'ad_group_member_removed' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; group_dn = $groupDn }
            }
        }
        if ($isTerminated) {
            $managedAdGroups = @()
            foreach ($mapping in @($policy.role_mappings)) { $managedAdGroups += @($mapping.ad_group_dns) }
            foreach ($groupDn in @($managedAdGroups | Where-Object { $_ } | Sort-Object -Unique)) {
                Remove-ADGroupMember -Identity $groupDn -Members $sam -Confirm:$false -ErrorAction SilentlyContinue
                Write-Audit -Event 'ad_group_member_removed' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; group_dn = $groupDn }
            }
            Disable-ADAccount -Identity $sam
            Write-Audit -Event 'ad_user_disabled' -Fields @{ worker_id = $worker.worker_id; upn = $worker.upn; sam_account_name = $sam }
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
