@description('The base name for the bot resources.')
param botName string = 'stamer-registration-bot'

@description('The location of the resources.')
param location string = resourceGroup().location

@description('The Microsoft App ID for the bot.')
param microsoftAppId string

@description('The Microsoft App Password for the bot.')
@secure()
param microsoftAppPassword string

var kvName = 'kv-${uniqueString(resourceGroup().id, botName)}'
var cosmosDbName = '${botName}-db'
var speechServiceName = '${botName}-speech'
var languageServiceName = '${botName}-language'

// 1. App Service Plan
resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: '${botName}-plan'
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
    size: 'B1'
    family: 'B'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

// 2. Web App with Managed Identity
resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: webAppName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    enabled: true
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'export PYTHONPATH=$PYTHONPATH:. && uvicorn app.main:app --host 0.0.0.0 --port 8000'
      alwaysOn: true
      appSettings: [

        {
          name: 'KEY_VAULT_URI'
          value: 'https://${kvName}${az.environment().suffixes.keyvaultDns}/'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
  }
}

// 3. Key Vault with Access Policy
resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: webApp.identity.principalId
        permissions: { secrets: [ 'get', 'list', 'set' ] }
      }
    ]
  }
}

// 4. Cosmos DB Account
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' = {
  name: cosmosDbName
  location: location
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0 } ]
  }
}

resource sqlDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-04-15' = {
  parent: cosmosDbAccount
  name: 'BotDatabase'
  properties: { resource: { id: 'BotDatabase' } }
}

resource sqlContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2023-04-15' = {
  parent: sqlDatabase
  name: 'Users'
  properties: {
    resource: {
      id: 'Users'
      partitionKey: { paths: [ '/email' ], kind: 'Hash' }
    }
  }
}

// 5. Speech Service
resource speechService 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: speechServiceName
  location: location
  kind: 'SpeechServices'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: speechServiceName
    publicNetworkAccess: 'Enabled'
  }
}

// 6. Language Service (New)
resource languageService 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: languageServiceName
  location: location
  kind: 'TextAnalytics'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: languageServiceName
    publicNetworkAccess: 'Enabled'
  }
}

// 7. Bot Service
resource botService 'Microsoft.BotService/botServices@2023-09-15-preview' = {
  name: botName
  location: 'global'
  kind: 'azurebot'
  sku: { name: 'F0' }
  properties: {
    displayName: 'Registration Bot'
    endpoint: 'https://${webApp.properties.defaultHostName}/api/messages'
    msaAppId: microsoftAppId
    msaAppType: 'SingleTenant'
    msaAppTenantId: subscription().tenantId
    schemaTransformationVersion: '1.3'
  }
}

// --- AUTOMATISCHE SECRETS IM KEY VAULT ---

resource secretAppId 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'microsoft-app-id'
  properties: { value: microsoftAppId }
}

resource secretAppPassword 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'microsoft-app-password'
  properties: { value: microsoftAppPassword }
}

resource secretCosmosEndpoint 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'cosmos-endpoint'
  properties: { value: cosmosDbAccount.properties.documentEndpoint }
}

resource secretCosmosKey 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'cosmos-key'
  properties: { value: cosmosDbAccount.listKeys().primaryMasterKey }
}

resource secretCosmosDb 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'cosmos-database'
  properties: { value: 'BotDatabase' }
}

resource secretCosmosContainer 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'cosmos-container'
  properties: { value: 'Users' }
}

resource secretSpeechKey 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'speech-key'
  properties: { value: speechService.listKeys().key1 }
}

resource secretSpeechRegion 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'speech-region'
  properties: { value: location }
}

resource secretLanguageKey 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'language-key'
  properties: { value: languageService.listKeys().key1 }
}

resource secretLanguageEndpoint 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'language-endpoint'
  properties: { value: 'https://${languageServiceName}.cognitiveservices.azure.com/' }
}

// --- ROLLENZUWEISUNGEN FÜR MANAGED IDENTITY ---

// Rolle: Cognitive Services User (ID: a97b65f3-24c7-4388-baec-2e87135dc908)
var cognitiveServicesUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')

resource speechRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechService.id, webApp.id, cognitiveServicesUserRoleDefinitionId)
  scope: speechService
  properties: {
    principalId: webApp.identity.principalId
    roleDefinitionId: cognitiveServicesUserRoleDefinitionId
    principalType: 'ServicePrincipal'
  }
}

resource languageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(languageService.id, webApp.id, cognitiveServicesUserRoleDefinitionId)
  scope: languageService
  properties: {
    principalId: webApp.identity.principalId
    roleDefinitionId: cognitiveServicesUserRoleDefinitionId
    principalType: 'ServicePrincipal'
  }
}

output webAppName string = webApp.name
output keyVaultName string = keyVault.name
