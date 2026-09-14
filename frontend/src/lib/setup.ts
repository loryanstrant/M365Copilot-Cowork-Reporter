/** Shared first-run setup content — imported by both SetupWizard (Settings) and
 *  the Setup guide page (/help) so the two can never drift apart. */

export const APP_DISPLAY_NAME = "M365 Copilot Cowork Reporter";

/** Microsoft Graph application permissions this solution needs. */
export const REQUIRED_PERMISSIONS = [
  {
    value: "AuditLogsQuery.Read.All",
    why: "Reads Purview audit for Cowork interactions — who used Cowork, when, and what it touched.",
  },
  {
    value: "User.Read.All",
    why: "Resolves users, departments and cost centres so usage and spend can be grouped.",
  },
];

/** Azure RBAC role needed on each subscription in scope, granted separately
 *  from the Graph permissions above. */
export const REQUIRED_AZURE_ROLE = {
  value: "Cost Management Reader",
  why: "Lets the collector pull daily Azure spend by resource group via the Cost Management Query API.",
};

/** A ready-to-run script that creates the app registration, adds the application
 *  permissions, grants admin consent, assigns the Cost Management Reader role,
 *  and prints the values to paste into the wizard. Permission GUIDs are resolved
 *  by name at runtime so nothing is hard-coded or can drift. */
export const SETUP_SCRIPT = `# Run in PowerShell 7 with the Microsoft Graph and Az SDKs.
# Requires a Global Administrator (or Privileged Role + Application admin),
# and Owner/User Access Administrator on the subscriptions you want cost for.
Install-Module Microsoft.Graph -Scope CurrentUser -Force  # first time only
Install-Module Az -Scope CurrentUser -Force               # first time only
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All"

$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
$needed  = "AuditLogsQuery.Read.All","User.Read.All"
$roles   = $graphSp.AppRoles | Where-Object { $needed -contains $_.Value }

$app = New-MgApplication -DisplayName "${APP_DISPLAY_NAME}" -RequiredResourceAccess @{
  ResourceAppId  = "00000003-0000-0000-c000-000000000000"
  ResourceAccess = @($roles | ForEach-Object { @{ Id = $_.Id; Type = "Role" } })
}
$sp = New-MgServicePrincipal -AppId $app.AppId

# Grant admin consent for both application permissions
foreach ($r in $roles) {
  New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id \`
    -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $r.Id | Out-Null
}

$secret = Add-MgApplicationPassword -ApplicationId $app.Id \`
  -PasswordCredential @{ DisplayName = "cowork-reporter"; EndDateTime = (Get-Date).AddYears(1) }

# Azure cost access: assign Cost Management Reader on each subscription in scope
Connect-AzAccount | Out-Null
foreach ($sub in (Get-AzSubscription)) {
  New-AzRoleAssignment -ApplicationId $app.AppId \`
    -RoleDefinitionName "Cost Management Reader" \`
    -Scope "/subscriptions/$($sub.Id)" -ErrorAction SilentlyContinue | Out-Null
  Write-Host "Cost Management Reader granted on $($sub.Name)"
}

Write-Host "Tenant ID:     $((Get-MgContext).TenantId)"
Write-Host "Client ID:     $($app.AppId)"
Write-Host "Client secret: $($secret.SecretText)"`;
