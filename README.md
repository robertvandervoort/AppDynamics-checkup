# AppDynamics-checkup
Scripts that output information about the state of your AppDynamics deployment

Simply modify the information at the top of the file before running it.
~~~
  # Replace with your AppDynamics API client details
  APPDYNAMICS_ACCOUNT_NAME = "account"
  APPDYNAMICS_API_CLIENT = "api-client-name"
  APPDYNAMICS_API_CLIENT_SECRET = "12345678-1234-1234-1234-123456789012"
~~~
If your controller is on-premise, you'll likely need to change the option for verify ssl to false as you may be using a self-signed certificate.

Also, choose what time range you'd like to look back to find the last reported date for your agents. There is some commentary about that in the file itself and all options should have good explanations. If you have questions, feel free to ask!

Create your API user in your AppDynamics controller - [click here for docs](https://docs.appdynamics.com/appd/23.x/latest/en/extend-appdynamics/appdynamics-apis/api-clients#id-.APIClientsv23.1-CreateAPIClientsCreate_API_Client)

Just follow the steps in the first part. You will not need to generate a token, the script will do this for you. You'll just need the name you named it and the client secret. Account name is just the first segment of your controller URL.

# appd-checkup.py
## What it does:
This script will iterate through every application, all of its tiers and nodes, and output into a output.csv file all of that inventory along with agents types and version and the last time that agent reported in in the last year. 

## Use cases:
* Inventory of your AppDynamics agents (reporting or otherwise)
* Targeting agents for upgrade
* Understanding what agents may not be working properly / are broken due to deployments or other changes
* Inventory of your monitored apps
* Determining monitoring coverage - comparing monitored elements to known architecture
* Determining what can be deleted from the controller UI like empty apps, empty tiers, etc.
* Probably more!
