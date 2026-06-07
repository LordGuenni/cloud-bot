@description('The base name for the bot resources.')
param botName string = 'stamer-registration-bot'

@description('The location of the resources.')
param location string = resourceGroup().location

@description('The Microsoft App ID for the bot.')
param microsoftAppId string

@description('The Microsoft App Password for the bot.')
@secure()
param microsoftAppPassword string

// 1. App Service Plan
resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: '${botName}-plan'
  location: location
  sku: {
    name: 'F1'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

// 2. Web App
resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: botName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        {
          name: 'MicrosoftAppId'
          value: microsoftAppId
        }
        {
          name: 'MicrosoftAppPassword'
          value: microsoftAppPassword
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
  }
}

// 3. Azure Bot Service
resource botService 'Microsoft.BotService/botServices@2023-09-15-preview' = {
  name: botName
  location: 'global'
  kind: 'azurebot'
  sku: {
    name: 'F0'
  }
  properties: {
    displayName: 'Registration Bot'
    endpoint: 'https://${webApp.properties.defaultHostName}/api/messages'
    msaAppId: microsoftAppId
    msaAppType: 'SingleTenant'
    msaAppTenantId: subscription().tenantId
    schemaTransformationVersion: '1.3'
  }
}


// 4. Cosmos DB
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' = {
  name: '${botName}-db'
  location: location
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
  }
}

output webAppName string = webApp.name
