param(
    [int]$InterfaceIndex = 5,
    [string]$ExpectedMacAddress = '08-26-AE-32-33-8C',
    [string]$IPv4Address = '192.168.1.200',
    [Parameter(Mandatory = $true)]
    [string]$ReportPath
)

# Run as administrator. Only configure the observed, DHCP-enabled device NIC.
# ActiveStore changes are temporary. No default gateway or DNS is added.
$ErrorActionPreference = 'Stop'
$taskChanged = $false
$taskExitCode = 1
$taskReport = [ordered]@{
    started_at = (Get-Date).ToString('o')
    interface_index = $InterfaceIndex
    expected_mac_address = $ExpectedMacAddress
    configured_address = $IPv4Address
    prefix_length = 24
    policy_store = 'ActiveStore'
    ok = $false
}

try {
    $taskParsedAddress = [System.Net.IPAddress]::Parse($IPv4Address)
    $taskAddressBytes = $taskParsedAddress.GetAddressBytes()
    if ($taskAddressBytes.Length -ne 4 -or $taskAddressBytes[0] -ne 192 -or
        $taskAddressBytes[1] -ne 168 -or $taskAddressBytes[2] -ne 1 -or
        $taskAddressBytes[3] -in @(0, 50, 55, 100, 255)) {
        throw 'Use a PC address in 192.168.1.0/24, excluding communication .50, manual .55 and PLC .100.'
    }
    $taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $taskPrincipal = [Security.Principal.WindowsPrincipal]::new($taskIdentity)
    if (-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Windows administrator permission is required to configure this NIC.'
    }
    $taskAdapter = Get-NetAdapter -InterfaceIndex $InterfaceIndex
    if ($taskAdapter.MacAddress -ne $ExpectedMacAddress -or $taskAdapter.Status -ne 'Up') {
        throw 'Adapter identity or link status changed; refusing to configure it.'
    }
    $taskInterface = Get-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4
    $taskAddresses = @(Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv4)
    $taskDefaultRoutes = @(Get-NetRoute -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 |
        Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' })
    $taskReport['before'] = @{
        adapter_name = $taskAdapter.Name
        description = $taskAdapter.InterfaceDescription
        mac_address = $taskAdapter.MacAddress
        dhcp = [string]$taskInterface.Dhcp
        addresses = @($taskAddresses | Select-Object IPAddress, PrefixLength, AddressState)
        default_routes = @($taskDefaultRoutes | Select-Object DestinationPrefix, NextHop)
    }
    if ($taskInterface.Dhcp -ne 'Enabled' -or $taskDefaultRoutes.Count -gt 0 -or
        @($taskAddresses | Where-Object { $_.IPAddress -notlike '169.254.*' }).Count -gt 0) {
        throw 'NIC is no longer DHCP/APIPA-only without a gateway; refusing to replace its configuration.'
    }
    $taskCommandOutput = & netsh.exe interface ipv4 set address "name=$InterfaceIndex" `
        source=static "address=$IPv4Address" mask=255.255.255.0 gateway=none store=active 2>&1
    $taskReport['netsh_output'] = ($taskCommandOutput | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "netsh failed with exit code $LASTEXITCODE"
    }
    $taskChanged = $true
    $taskAddressReady = $false
    for ($taskAttempt = 0; $taskAttempt -lt 20; $taskAttempt++) {
        $taskAssignedAddress = Get-NetIPAddress -InterfaceIndex $InterfaceIndex `
            -AddressFamily IPv4 -IPAddress $IPv4Address -ErrorAction SilentlyContinue
        if ($taskAssignedAddress.AddressState -eq 'Duplicate') {
            throw 'Windows detected a duplicate address; restoring DHCP.'
        }
        if ($taskAssignedAddress.AddressState -eq 'Preferred') {
            $taskAddressReady = $true
            break
        }
        Start-Sleep -Milliseconds 400
    }
    if (-not $taskAddressReady) {
        throw 'The configured address did not become usable; restoring DHCP.'
    }
    $taskReport['after'] = @(Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 |
        Select-Object IPAddress, PrefixLength, AddressState)
    $taskReport['ok'] = $true
    $taskExitCode = 0
} catch {
    $taskReport['error'] = $_.Exception.Message
    if ($taskChanged) {
        $taskRestoreOutput = & netsh.exe interface ipv4 set address "name=$InterfaceIndex" source=dhcp store=active 2>&1
        $taskReport['restore_exit_code'] = $LASTEXITCODE
        $taskReport['restore_output'] = ($taskRestoreOutput | Out-String).Trim()
    }
} finally {
    $taskReport['finished_at'] = (Get-Date).ToString('o')
    $taskReport | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}
exit $taskExitCode
