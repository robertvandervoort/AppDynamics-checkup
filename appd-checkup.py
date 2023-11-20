# This script requires you to create an API key in AppDynamics and add the account owner and administrator roles to it.
# you will need to replace the value below with the values related to the controller you would like to query
# and the API client name and secret. The script will look at the last year of data to determine the last time agents connected.
# If no availability metrics were registered in over 12 months for the tier, you will see OUT OF RANGE in the resulting CSV file.
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
appdynamics_API_client_name = "API-client"
appdynamics_API_client_secret = "123456abc-1234-1234-1234-1234567890ab"

# Replace with the desired output CSV file path
output_csv_file_path = "output.csv"

# Set the base URL for the AppDynamics REST API
base_url = "https://"+appdynamics_account_name+".saas.appdynamics.com/controller/rest"
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

# Get a list of all applications
applications_url = base_url + "/applications?output=json"
print("Retrieving Applications from "+applications_url)
applications_response = requests.get(applications_url, headers=__session__.headers)

applications_data = applications_response.json()

# Open the output CSV file for writing
print("Opening CSV file " + output_csv_file_path + " for writing...")
with open(output_csv_file_path, "w") as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow(["Application", "Description", "Tier", "Last up", "Last up count", "Node", "machineAgentVersion", "agentType", "appAgentVersion"])

    # Iterate over each application
    print("Iterating over each application to fetch tier and node data...")
    for application in applications_data:
        application_name = application["name"]
        application_description = application["description"]
        application_id = application["id"]
        print("----" + application_name)

        # Get a list of all tiers for the application
        tiers_url = base_url + "/applications/" + str(application_id) + "/tiers?output=json"
        print(" ---Fetching tier data from " + tiers_url)
        tiers_response = requests.get(tiers_url, headers=__session__.headers)
        tiers_data = tiers_response.json()

        # Iterate over each tier for the application
        for tier in tiers_data:
            tier_name = tier["name"]
            tier_id = tier["id"]
            tier_type = tier["type"]
            tier_agentType = tier["agentType"]
            print("    " + tier_name)
            
            #grab tier availability data
            print("    Querying for tier availability...")
            availability_values = get_metric(application_name, tier_name)
            dt, value = availability_values
            print("        Tier last seen on " + str(dt) + " " + str(value) + " nodes seen.")

            # Get a list of all nodes for the tier
            nodes_url = base_url + "/applications/" + str(application_id) + "/tiers/" + str(tier_id) + "/nodes?output=json"
            print("    ----Fetching node data from " + nodes_url)
            nodes_response = requests.get(nodes_url, headers=__session__.headers)
            nodes_data = nodes_response.json()

            # Iterate over each node for the tier and write to the CSV
            for node in nodes_data:
                node_name = node["name"]
                node_machineAgentVersion = node["machineAgentVersion"]
                node_appAgentVersion = node["appAgentVersion"]
                node_agentType = node["agentType"]
                print("        " + node_name)
                csv_writer.writerow([application_name, application_description, tier_name, dt, value, node_name, node_machineAgentVersion, node_agentType, node_appAgentVersion])