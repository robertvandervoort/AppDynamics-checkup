# This script requires you to create an API key in AppDynamics and add the account owner and administrator roles to it.
# you will need to replace the value below with the values related to the controller you would like to query
# and the API client name and secret. 
# for questions / help contact Robert Vandervoort - rvander2@cisco.com
# CHEERS!

import requests
import json
import csv
import datetime
import urllib.parse

# print debug info
global debug
debug = False

# Replace with your AppDynamics API client details
appdynamics_account_name = "customer1"
appdynamics_API_client_name = "your_API-client_name"
appdynamics_API_client_secret = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Replace with the desired output CSV file path
output_csv_file_path = appdynamics_account_name + "-output-servers.csv"

# Set the base URL for the AppDynamics REST API
base_url = "https://"+appdynamics_account_name+".saas.appdynamics.com/controller"
print("Accessing controller at: "+base_url)

#------------ Define functions to use --------------
#get our OAUTH token
def connect(account, apiClient, secret):
    global __account__
    global __session__
    __session__ = requests.Session()
    loggedIn = False

    __account__ = account
    data = {
        'grant_type': 'client_credentials',
        'client_id': apiClient,
        'client_secret': secret
    }
    url = "https://" + __account__ + ".saas.appdynamics.com/controller/api/oauth/access_token?grant_type=client_credentials&client_id=" + apiClient + "@" + __account__ +"&client_secret=" + secret
    payload = {}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    response = __session__.request("POST", url, headers=headers, data=payload)
    
    if debug:
        print ("Headers = " + str(__session__.headers))
    
    if (response.status_code == 200):
        json_response = json.loads (response.text)
        if debug:
            print ("Auth: " + json_response['access_token'])
        __session__.headers['X-CSRF-TOKEN'] = json_response['access_token']
        __session__.headers['Authorization'] = 'Bearer ' + json_response['access_token']

        loggedIn = True
        print("Logged in...")
    else:
        print("Query failed: " + response.raise_for_status())
    return loggedIn

#make tier names compatible for the REST URL
def urlencode_string(text):
    # Replace spaces with '%20'
    text = text.replace(' ', '%20')

    # Encode the string using the 'safe' scheme
    safe_characters = '-_.!~*\'()[]+:;?,/=$&%'
    encoded_text = urllib.parse.quote(text, safe=safe_characters)

    return encoded_text

# fetch last known app agent availability info
def get_metric(application_name, tier_name, ):
    # fetch last known app agent availability info
    tier_name = urlencode_string(tier_name)
    metric_path = "Application%20Infrastructure%20Performance%7C" + tier_name + "%7CAgent%7CApp%7CAvailability"
    #12 month look back
    metric_duration_mins = 525600
    metric_rollup = "false"
    metric_url = base_url + "/applications/" + application_name + "/metric-data?metric-path=" + metric_path + "&time-range-type=BEFORE_NOW&duration-in-mins=" + str(metric_duration_mins) + "&rollup=" + metric_rollup + "&output=json"

    #get metric data
    print("Retrieving metric from "+metric_url)
    metric_response = requests.get(metric_url, headers=__session__.headers)

    json_data=metric_response.json()
    
    if debug:
        print(metric_response.text)
    
    #do some error handling for missing data / agents down past the time range
    if metric_response.text == "[ ]":
        dt = "NO DATA"
        value = "NAN"
        return dt, value
    elif (json_data[-1]['metricName'] == "METRIC DATA NOT FOUND"):
        dt = "OUTSIDE TIME RANGE"
        value = "NAN"
        return dt, value

    last_start_time_millis = json_data[-1]['metricValues'][-1]['startTimeInMillis']
    value = json_data[-1]['metricValues'][-1]['value']
    
    #convert EPOCH to human readable datetime - we have to divide by 1000 because we show EPOCH in ms not seconds
    dt = datetime.datetime.fromtimestamp((last_start_time_millis/1000))
    
    return dt, value

#------------ Do stuff -----------------#
#get XCSRF token for use in this session
connect(appdynamics_account_name, appdynamics_API_client_name, appdynamics_API_client_secret)

'''debug
#Get a list of all servers
servers_url = base_url + "/sim/v2/user/machines"
print("Retrieving Servers from " + servers_url)
servers_response = requests.get(servers_url, headers=__session__.headers)

servers_data = servers_response.json()

#json_formatted_str = json.dumps(servers_data[-1], indent=2)
#print(json_formatted_str)
'''

'''
servers_data = {
  "hostId": "c833123126c4",
  "name": "c833123126c4",
  "hierarchy": [
    "Containers"
  ],
  "properties": {
    "AppDynamics|Machine Type": "NON_CONTAINER_MACHINE_AGENT",
    "Container|Hostname": "c833123126c4",
    "Container|Id": "c833123126c4",
    "Container|Image|Name": "gdsglobalacr.azurecr.io/monitor/2.0/chevron-aks-monitor:prodlatest",
    "Container|K8S|PodName": "aks-monitoring-cj-app-28343070-8fn9m",
    "Container|Name": "aks-monitoring-po",
    "Container|Image|Id": "gdsglobalacr.azurecr.io/monitor/2.0/chevron-aks-monitor@sha256:ed651316397201aef3dcede6a3d15335a0cb82079fcd32c636ecf8958d22891e",
    "Container|Started At": "",
    "Container|Created At": "2023-11-21T16:30:00Z",
    "Container|K8S|Namespace": "gds"
  },
  "tags": {},
  "agentConfig": {
    "rawConfig": {
      "_features": {
        "features": [
          "basic",
          "sim"
        ]
      },
      "_agentRegistrationRequestConfig": {
        "machineInfo": "os.name=linux|os.arch=amd64|os.version=unknown",
        "jvmInfo": "",
        "installDirectory": "",
        "agentVersion": "4.5.16.0",
        "autoRegisterAgent": true
      },
      "_agentRegistrationSupplementalConfig": {
        "simMachineType": "CONTAINER",
        "hostSimMachineId": 859335,
        "hostName": "aks-monitoring-cj-app-28343070-8fn9m",
        "containerType": "NON_APM"
      },
      "_machineInstanceRegistrationRequestConfig": {
        "forceMachineInstanceRegistration": true
      }
    }
  },
  "id": 1396730,
  "memory": {},
  "volumes": [],
  "cpus": [],
  "networkInterfaces": [],
  "controllerConfig": {
    "rawConfig": {
      "_features": {
        "features": [
          "sim"
        ],
        "reason": {
          "message": "",
          "code": ""
        }
      },
      "_agentRegistrationSupplementalConfig": {
        "simMachineType": "CONTAINER",
        "hostSimMachineId": 859335,
        "hostName": "aks-monitoring-cj-app-28343070-8fn9m",
        "containerType": "NON_APM"
      },
      "_machineInstanceRegistrationRequestConfig": {
        "forceMachineInstanceRegistration": true
      },
      "_agentRegistrationRequestConfig": {
        "machineInfo": "os.name=linux|os.arch=amd64|os.version=unknown",
        "jvmInfo": "",
        "installDirectory": "",
        "agentVersion": "4.5.16.0",
        "autoRegisterAgent": true
      }
    }
  },
  "simEnabled": true,
  "simNodeId": 1976088,
  "dynamicMonitoringMode": "KPI",
  "type": "CONTAINER",
  "historical": false
}
'''

#Get a list of all servers
servers_url = base_url + "/sim/v2/user/machines"
print("Retrieving Servers from " + servers_url)
servers_response = requests.get(servers_url, headers=__session__.headers)

servers_data = servers_response.json()
servers_data_count = (len(servers_data))

print("servers_data length: " + str((servers_data_count)))

# Open the output CSV file for writing
print("Opening CSV file " + output_csv_file_path + " for writing...")
with open(output_csv_file_path, "w") as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow(["hierarchy", "hostId", "name", "namespace", "podName", "containerName", "containerImage", "tags", "memory", "volumes", "cpus", "machineInfo", "agentVersion", "simEnabled", "type", "DMM", "historical"])

    # Iterate over each server
    print("Iterating over each server to fetch info...")
    
    for server in servers_data:
        namespace = podName = containerName = containerImage = ""
        machineInfo = server["agentConfig"]["rawConfig"]["_agentRegistrationRequestConfig"]["machineInfo"]
        agentVersion = server["agentConfig"]["rawConfig"]["_agentRegistrationRequestConfig"]["agentVersion"]

        if (server["type"] == "CONTAINER"):
            if ("Container|K8S|Namespace" in server["properties"]):
                namespace = server["properties"]["Container|K8S|Namespace"]
            else:
                # Handle the case where the key does not exist
                print("The key 'Container|K8S|Namespace' does not exist in the dictionary")

            if ("Container|K8S|PodName" in server["properties"]):
                podName = server["properties"]["Container|K8S|PodName"]
            else:
                # Handle the case where the key does not exist
                print("The key 'Container|K8S|PodName' does not exist in the dictionary")
            
            if ("Container|Name" in server["properties"]):
                containerName = server["properties"]["Container|Name"]
            else:
                # Handle the case where the key does not exist
                print("The key 'containerName' does not exist in the dictionary")
            
            if ("Container|Image|Name" in server["properties"]):
                containerImage = server["properties"]["Container|Image|Name"]
            else:
                # Handle the case where the key does not exist
                print("The key 'Container|Image|Name' does not exist in the dictionary")
                
        csv_writer.writerow([server["hierarchy"], server["hostId"], server["name"], namespace, podName, containerName, containerImage, server["tags"], server["memory"], server["volumes"], server["cpus"], machineInfo, agentVersion, server["simEnabled"], server["type"], server["dynamicMonitoringMode"], server["historical"]])