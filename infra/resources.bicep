// All resources for the M365 Copilot Cowork Reporter, deployed into one RG:
// Log Analytics, Container Registry, managed identity, Container Apps
// Environment, a PostgreSQL flexible server, and the api + worker container apps.
@description('Location for all resources.')
param location string

@minLength(3)
@description('Stable token used to name resources uniquely.')
param resourceToken string

@description('Tags applied to every resource (must include azd-env-name).')
param tags object

@secure()
param postgresAdminPassword string
@secure()
param fernetKey string
@secure()
param secretKey string
param adminUsername string
@secure()
param adminPassword string

// Workload prefix so every resource is instantly identifiable in the portal.
var workload = 'cowork'
var abbrs = {
  registry: 'acr'
  identity: 'id'
  logs: 'log'
  env: 'cae'
  postgres: 'psql'
}
var pgAdminLogin = 'coworkadmin'
var pgDatabaseName = 'cowork'

// --- Observability ------------------------------------------------------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${workload}-${abbrs.logs}-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// --- Identity + registry ------------------------------------------------
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${workload}-${abbrs.identity}-${resourceToken}'
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: '${workload}${abbrs.registry}${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

var acrPullRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Database -----------------------------------------------------------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: '${workload}-${abbrs.postgres}-${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }

  resource database 'databases@2024-08-01' = {
    name: pgDatabaseName
  }

  resource allowAzure 'firewallRules@2024-08-01' = {
    name: 'AllowAllAzureServices'
    properties: {
      startIpAddress: '0.0.0.0'
      endIpAddress: '0.0.0.0'
    }
  }
}

var databaseUrl = 'postgresql+psycopg://${pgAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${pgDatabaseName}?sslmode=require'

// --- Container Apps environment ----------------------------------------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${workload}-${abbrs.env}-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var sharedSecrets = [
  { name: 'database-url', value: databaseUrl }
  { name: 'fernet-key', value: fernetKey }
  { name: 'secret-key', value: secretKey }
  { name: 'admin-password', value: adminPassword }
]

var sharedEnv = [
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'FERNET_KEY', secretRef: 'fernet-key' }
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'ADMIN_USERNAME', value: adminUsername }
  { name: 'ADMIN_PASSWORD', secretRef: 'admin-password' }
  { name: 'APP_ENV', value: 'production' }
]

// Entra sign-in is performed by the app itself, using the app registration
// entered in Settings. There is no platform auth (Easy Auth) to configure here.
var apiSecrets = sharedSecrets

// --- API (web) container app -------------------------------------------
resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${workload}-api-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
      secrets: apiSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(sharedEnv, [
            { name: 'RUN_MIGRATIONS_ON_STARTUP', value: 'true' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [acrPull]
}

// --- Worker container app (no ingress) ---------------------------------
resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${workload}-worker-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'worker' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(sharedEnv, [
            { name: 'RUN_MIGRATIONS_ON_STARTUP', value: 'false' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [acrPull]
}

output registryLoginServer string = registry.properties.loginServer
output apiUri string = 'https://${api.properties.configuration.ingress.fqdn}'
