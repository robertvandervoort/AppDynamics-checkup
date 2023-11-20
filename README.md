# AppDynamics-checkup
Scripts that output information about the state of your AppDynamics deployment

Simply modify the information at the top of the file before running it.
~~~
  # Replace with your AppDynamics API client details
  appdynamics_account_name = "customer1"
  appdynamics_API_client_name = "API-client"
  appdynamics_API_client_secret = "123456abc-1234-1234-1234-1234567890ab"
~~~
Create your API user in your AppDynamics controller - [click here for docs](https://docs.appdynamics.com/appd/23.x/latest/en/extend-appdynamics/appdynamics-apis/api-clients#id-.APIClientsv23.1-CreateAPIClientsCreate_API_Client)

Just follow the steps in the first part. You will not need to generate a token, the script will do this for you. You'll just need the name you named it and the client secret. Account name is just the first segment of your controller URL.

# appd-checkup.py
## What it does:
This script will iterate through every application, all of its tiers and nodes, and output into a output.csv file all of that inventory along with agents types and version and the last time that agent reported in in the last year. 

## Use cases:
* Inventory of your AppDynamics agents (reporting or otherwise)
* Targeting agents for upgrade
* Understanding what agents may not be working properly / are broken due to deployments or other cahhgnes
* Inventory of your monitored apps
* Determining monitoring coverage - comparing monitored elements to known architecture
* Determining what can be deleted from the controller UI (deprecated apps)
* Probably more!
