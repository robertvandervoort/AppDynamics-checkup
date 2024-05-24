# This script requires you to create an API key in AppDynamics and add the account owner and administrator roles to it.
# you will need to replace the value below with the values related to the controller you would like to query
# and the API client name and secret. The script will look at the last year of data to determine the last time agents connected.
# If no availability metrics were registered in over 12 months for the tier, you will see OUT OF RANGE in the resulting CSV file.
# for questions / help contact Robert Vandervoort - rvander2@cisco.com
# CHEERS!

import sys
import json
import csv
import datetime
import time
import urllib.parse
import requests

#--- CONFIGURATION SECTION ---
# print debug info set DEBUG to True if you need to get RICH details about what is going on..
# will flood the console when running against a decent sized controller.
DEBUG = False

#Replace with your AppDynamics API client details
APPDYNAMICS_ACCOUNT_NAME = "account"
APPDYNAMICS_API_CLIENT = "api_client_name"
APPDYNAMICS_API_CLIENT_SECRET = "secret"

#For reporting on a single application use the ID from the query seen in the URL in AppD,
application_id = "" # leave this as is and do not comment it out

# Now off by default - setting this to True will write a row in the output CSV representing the number of app nodes seen on a tier and the last time that tier availability was seen. 
# Initially this was useful ro help create this script but now it kind of just confuses the data so we are not grabbing it by default.
WRITE_TIER_AVAILABILITY_DATA = False

# Replace with the desired output CSV file path and name or leave as it to create dynamically (recommended)
#OUTPUT_CSV_FILE = "output.csv"
OUTPUT_CSV_FILE = APPDYNAMICS_ACCOUNT_NAME+"_servers_"+datetime.date.today().strftime("%m-%d-%Y")+".csv"

# Set the base URL for the AppDynamics REST API
# --- replace this with your on-prem controller URL if you're on prem
BASE_URL = "https://"+APPDYNAMICS_ACCOUNT_NAME+".saas.appdynamics.com"

# Verify SSL certificates - should only be set false for on-prem controllers. Use this if the script fails right off the bat and gives you errors to the point..
VERIFY_SSL = True

"""
Set this METRIC_DURATION_MINS variable to how far you want to look back in time to find the last time agents 
reported in. The value is in minutes. Depending on how far you look back, data will be aggregated. If you go 
back 12 months, you'll get 1 hour data points. Data is only retained for 13 months max. The father you go back 
the longer the script will take to run. I would recommend for your first time running this you go back a year 
or since you deployed, whichever is less. For subsequent runs, decrease the time considerably. Three examples 
follow. Ensure only one option is uncommented.
"""
#METRIC_DURATION_MINS = 525600 #12 months
METRIC_DURATION_MINS = 43800 #1 month
#METRIC_DURATION_MINS = 1440 #1 day
#METRIC_DURATION_MINS = 240 #4 hours
#METRIC_DURATION_MINS = 5 #5 mins

"""
Also, metric rollups may be considered when using broader time ranges, however the last up date will represent 
the earliest data point in the series instead of the actual last time it reported in. see the doc:
https://docs.appdynamics.com/appd/24.x/latest/en/extend-appdynamics/appdynamics-apis/metric-and-snapshot-api#MetricandSnapshotAPI-DataRetentionforMetricandSnapshotAPI
"""
METRIC_ROLLUP = "false"

#manages token expiration - do not change these values
last_token_fetch_time = ""
token_expiration = 300
expiration_buffer = 30

#---FUNCTION DEFINITIONS
def authenticate(state):
    """get XCSRF token for use in this session"""
    if state == "reauth":
        print("Obtaining a freah authentication token.")
    if state == "initial":
        print("Begin login.")
    
    connect(APPDYNAMICS_ACCOUNT_NAME, APPDYNAMICS_API_CLIENT, APPDYNAMICS_API_CLIENT_SECRET)
    
    return

def is_token_valid():
    """Checks if the access token is valid and not expired."""
    if DEBUG:
        print("Checking token validity...")

    if __session__ is None:
        if DEBUG:
            print("__session__ not found or empty.")
        return False

    # Conservative buffer (e.g., 30 seconds before expiration)
    if DEBUG:
        print(f"__session__: {__session__}")
    return time.time() < (token_expiration + last_token_fetch_time - expiration_buffer)

def connect(account, apiclient, secret):
    """Connects to the AppDynamics API and retrieves an OAuth token."""
    global __session__, last_token_fetch_time, token_expiration
    __session__ = requests.Session()

    url = f"{BASE_URL}/controller/api/oauth/access_token?grant_type=client_credentials&client_id={apiclient}@{account}&client_secret={secret}"
    payload = {} 
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    print(f"Logging into the controller at: {BASE_URL}")

    @handle_rest_errors  # Apply the error handling decorator
    def make_auth_request():
        response = __session__.request(
            "POST",
            url,
            headers=headers,
            data=payload,
            verify=VERIFY_SSL
        )
        return response

    auth_response, status = make_auth_request()
    if DEBUG:
        print(f"Authentication response:{auth_response} = {status}")

    # Assuming auth_response isn't None if no errors occurred
    if status == "valid":
        if auth_response:
            json_response = auth_response.json()
            last_token_fetch_time = time.time()
            token_expiration = json_response['expires_in']
    else:
        print(f"Unable to log in at: {BASE_URL}")
        print("Please check your controller URL and try again.")
        sys.exit(9)

    __session__.headers['X-CSRF-TOKEN'] = json_response['access_token']
    __session__.headers['Authorization'] = f'Bearer {json_response["access_token"]}'
    
    print("Authenticated with controller.")
    
    if DEBUG:
        print(f"Last token fetch time: {last_token_fetch_time}")
        print(f"Token expires in: {json_response['expires_in']}")
        print(f"Session headers: {__session__.headers}")
    
    return True

def handle_rest_errors(func):
    """for handling REST calls"""
    def inner_function(*args, **kwargs):
        error_map = {
            400: "Bad Request - The request was invalid.",
            401: "Unauthorized - Authentication failed.",
            403: "Forbidden - You don't have permission to access this resource.",
            404: "Not Found - The resource could not be found.",
            500: "Internal Server Error - Something went wrong on the server.",
        }

        try:
            response = func(*args, **kwargs)
            response.raise_for_status()
            return response, "valid"
        except requests.exceptions.HTTPError as err:
            error_code = err.response.status_code
            error_explanation = error_map.get(error_code, "Unknown HTTP Error")
            print(f"HTTP Error: {error_code} - {error_explanation}")
            return error_explanation, "error"
        except requests.exceptions.RequestException as err:
            if isinstance(err, requests.exceptions.ConnectionError):
                print("Connection Error: Failed to establish a new connection.")
                return err, "error"
            else: 
                print(f"Request Exception: {err}") 
                return err, "error"
        except Exception:  
            error_type, error_value, _ = sys.exc_info() 
            print(f"Unexpected Error: {error_type.__name__}: {error_value}")
            return error_value, "error"

    return inner_function

def urlencode_string(text):
    """make app, tier or node names URL compatible for the REST call"""
    # Replace spaces with '%20'
    text = text.replace(' ', '%20')

    # Encode the string using the 'safe' scheme
    safe_characters = '-_.!~*\'()[]+:;?,/=$&%'
    encoded_text = urllib.parse.quote(text, safe=safe_characters)

    return encoded_text

@handle_rest_errors
def get_metric(object_type, app, tier, agenttype, node):
    """fetches last known agent availability info from tier or node level."""
    tier = urlencode_string(tier)
    app = urlencode_string(app)
    if DEBUG:
        print(f"        --- Begin get_metric({object_type},{app},{tier},{agenttype},{node})")

    if object_type == "node":
        print("        --- Querying node availability.")
        if agenttype == "MACHINE_AGENT":
            metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CIndividual%20Nodes%7C" + node + "%7CAgent%7CMachine%7CAvailability"
        else:
            metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CIndividual%20Nodes%7C" + node + "%7CAgent%7CApp%7CAvailability"
    
    elif object_type == "tier":
        print("        --- Querying tier availability.")
        metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CAgent%7CApp%7CAvailability"
        
    # If the machine agents were assigned a tier, the tier reads as an app agent. The availability data would be here instead
    # metric_path = "Application%20Infrastructure%20Performance%7C" + tier_name + "%7CAgent%7CMachine%7CAvailability"
    # future enhancement will reflect the number and last seen for machine agent tiers.

    metric_url = BASE_URL + "/controller/rest/applications/" + app + "/metric-data?metric-path=" + metric_path + "&time-range-type=BEFORE_NOW&duration-in-mins=" + str(METRIC_DURATION_MINS) + "&rollup=" + METRIC_ROLLUP + "&output=json"
                                
    #get metric data
    if DEBUG:
        print("        --- metric url: " + metric_url)

    metric_response = requests.get(
        metric_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )

    return metric_response

def handle_metric_response(metric_data, metric_data_status):
    """Processes returned metric JSON data"""
    if DEBUG:
        print("        --- handle_metric_response() - Handling metric data...")
        print(f"        --- handle_metric_response() - metric_data: {metric_data}")
        print(f"        --- handle_metric_response() - metric_data type: {type(metric_data)}")
        print(f"        --- handle_metric_response() - metric_data_status: {metric_data_status}")

    if metric_data_status == "valid":
        if metric_data == []:
            dt = "METRIC DATA NOT FOUND IN TIME RANGE"
            print(dt)
            return dt, metric_data_status
        if metric_data[-1]['metricName'] == "METRIC DATA NOT FOUND":
            dt = "METRIC DATA NOT FOUND IN TIME RANGE"
            print(dt)
            return dt, metric_data_status
        elif metric_data[-1]['metricValues'][-1]['startTimeInMillis']:
            if DEBUG:
                print("        --- Performing datetime calculation on metric data")
            last_start_time_millis = metric_data[-1]['metricValues'][-1]['startTimeInMillis']
            if DEBUG:
                print(f"            --- startTimeInMillis: {last_start_time_millis}")
            #convert EPOCH to human readable datetime - we have to divide by 1000 because we show EPOCH in ms not seconds
            if DEBUG:
                print("            --- Converting EPOCH to datetime")
            epoch = (last_start_time_millis/1000)
            dt = datetime.datetime.fromtimestamp(epoch)
            value = metric_data[-1]['metricValues'][-1]['current']
            if DEBUG:
                print(f"            --- dt: {dt} value: {value}")
            return dt, value

    elif metric_data_status == "empty":
        dt = "EMPTY RESPONSE"
        return dt, metric_data_status
    
    elif metric_data_status == "error":
        dt = "ERROR"
        return dt, metric_data_status
    
    elif metric_data == []:
        dt = "EMPTY RESPONSE"
        return dt, metric_data_status

def validate_json(response):
    """validation function to parse into JSON and catch empty sets returned from our API requests"""
    if DEBUG:
        print("        --- validate_json()")
    if not response:
        #this state is NOT always an error. Sometimes there are old tiers with no nodes anymore. Same for apps.
        if DEBUG:
            print("        ---- No response object was found.")
        return [], "empty"

    try:
        if DEBUG:
            print(f"        --- validate_json() - incoming response type:: {type(response)}")
            print(f"        --- validate_json() - incoming response:{response}")
        if not isinstance(response, requests.Response):
            if DEBUG:
                print(f"        --- validate_json() - length: {len(response)}") 
                print("        --- validate_json() - unpacking response")
            #unpack response
            data, data_status = response
            
            #pass error and exceptions from the response along to the main code
            if data_status == "error":
                return data, data_status
            else:
                data = data.json()
                if DEBUG:
                    print(f"        --- validate_json() - data: {data} data_status: {data_status}")
                return data, data_status
        else:
            # parse the request object into a json object and its status
            json_data = response.json()

            if DEBUG:
                print(f"        --- validate_json() - data: {json_data}")
                print(f"        --- validate_json() - json_data type: {type(json_data)}")  

            # check for empty JSON object
            if not json_data:
                if DEBUG:
                    print("\n            ---- The resulting JSON object judged as empty")
                    print(f"            ---- data.text {data.text} , json_data {json_data}")
                return None, "empty"

            return json_data, "valid"

    except json.JSONDecodeError:
        # The data is not valid JSON.
        if DEBUG:
            print("The data is not valid JSON.")
        return None, "error"

@handle_rest_errors
def get_applications():
    """Get a list of all applications"""
    print("--- Fetching applications...")
    
    if not is_token_valid():
        authenticate("reauth")

    if application_id:
        #chosen when user supplied an app id in the config
        applications_url = BASE_URL + "/controller/rest/applications/" + str(application_id) + "?output=json"
        if DEBUG:
            print("--- from "+applications_url)
    else:
        applications_url = BASE_URL + "/controller/rest/applications?output=json"
        if DEBUG:
            print("--- from "+applications_url)
    
    applications_response = requests.get(
        applications_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )

    if DEBUG:
        print(applications_response.text)
    return applications_response

@handle_rest_errors
def get_tiers(application_id):
    """Gets the tiers in the application"""
    if not is_token_valid():
        authenticate("reauth")
    
    tiers_url = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/tiers?output=json"
    
    if DEBUG:
        print("    --- Fetching tiers from: "+ tiers_url)
    else:
        print("    --- Fetching tiers...")

    tiers_response = requests.get(
        tiers_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )
    if DEBUG:
        print(f"    --- get_tiers response: {tiers_response.text}")

    return tiers_response

@handle_rest_errors
def get_nodes(application_id, tier_id):
    """Gets the nodes in a tier"""
    if not is_token_valid():
        authenticate("reauth")

    nodes_url = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/tiers/" + str(tier_id) + "/nodes?output=json"
    if DEBUG:
        print(f"        --- Fetching node data from {nodes_url}.")
    else:
        print("        --- Fetching nodes from tier.")

    nodes_response = requests.get(
        nodes_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )

    return nodes_response

@handle_rest_errors
def get_snapshots(application_id):
    if not is_token_valid():
        authenticate("reauth")

    snapshots_url = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/request-snapshots?time-range-type=BEFORE_NOW&duration-in-mins=" + str(METRIC_DURATION_MINS) + "&first-in-chain=true&maximum-results=1000000&output=json"

    if DEBUG:
        print("    --- Fetching snapshots from: "+ snapshots_url)
    else:
        print("    --- Fetching snapshots...")

    snapshots_response = requests.get(
        snapshots_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )
    #if DEBUG:
    #    print(f"    --- get_snapshots response: {snapshots_response.text}")

    return snapshots_response

#@handle_rest_errors
def get_bts(application_id): 
    '''retrieves business transactions list from the application'''
    
    if not is_token_valid():
        authenticate("reauth")

    bts_url = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/business-transactions"

    if DEBUG:
        print("    --- Fetching bts from: "+ bts_url)
    else:
        print("    --- Fetching bts...")

    bts_response = requests.get(
        bts_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )
    #if DEBUG:
    #    print(f"    --- get_bts response: {bts_response.text}")

    #convert the XML to JSON
    xml_data = bts_response.text

    # Convert XML to an ordered dictionary
    dict_data = xmltodict.parse(xml_data)
    
    #if DEBUG:
    #    print("    --- BTs output:")
    #    print(json.dumps(dict_data, indent=4)) 
    
    # Create the in-memory map
    transaction_name_map = {}
    
    # Extract data and populate the map
    for business_transaction in dict_data["business-transactions"]["business-transaction"]:
        transaction_id = int(business_transaction["id"])  # Now 'id' is  accessed directly
        transaction_name = business_transaction["name"]
        entry_point_type = business_transaction.get("entryPointType")
        tier_name = business_transaction.get("tierName")

        transaction_name_map[transaction_id] = {
            "name": transaction_name,
            "entryPointType": entry_point_type,
            "tierName": tier_name
        }
    
    return transaction_name_map

@handle_rest_errors
def get_servers():
    '''Get a list of all servers'''
    servers_url = BASE_URL + "/controller/sim/v2/user/machines"
    if DEBUG:
        print(f"    --- Retrieving Servers from {servers_url}")
    else:
        print("    --- Retrieving Servers...")
              
    servers_response = requests.get(
        servers_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )

    if DEBUG:
        servers_data = servers_response.json()
        servers_data_count = (len(servers_data))
        print("servers_data length: " + str((servers_data_count)))

    return servers_response

@handle_rest_errors
def get_healthRules(application_id):
    '''retrieves health rules from application(s)'''

    if not is_token_valid():
        authenticate("reauth")

    healthRules_url = BASE_URL + "/controller/alerting/rest/v1/applications/" + str(application_id) + "/health-rules"

    if DEBUG:
        print(f"    --- Fetching health rules from: {healthRules_url}")
    else:
        print("    --- Fetching health rules...")

    healthRules_response = requests.get(
        healthRules_url,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )
    if DEBUG:
        print(f"    --- get_healthRules response: {healthRules_response.text}")

    return healthRules_response    

#--- MAIN
authenticate("initial")

servers_response = get_servers()
servers, servers_status = validate_json(servers_response)

# Open the output CSV file for writing
print("Opening CSV file " + OUTPUT_CSV_FILE + " for writing...")
with open(OUTPUT_CSV_FILE, "w") as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow(["hierarchy", "hostId", "name", "namespace", "podName", "containerName", "containerImage", "containerCreated", "containerStarted", "tags", "memory", "volumes", "cpus", "machineInfo", "agentVersion", "simEnabled", "type", "DMM", "historical"])

    # Iterate over each server
    print("Iterating over each server to fetch info...")
    
    for server in servers:
        '''
        server = {
            "agentConfig": {
                "rawConfig": {
                    "_agentRegistrationRequestConfig": {
                        "agentVersion": "4.5.16.0",
                        "autoRegisterAgent": true,
                        "installDirectory": "",
                        "jvmInfo": "",
                        "machineInfo": "os.name=linux|os.arch=amd64|os.version=unknown"
                    },
                    "_agentRegistrationSupplementalConfig": {
                        "containerType": "NON_APM",
                        "hostName": "catqa3livelsi-app-5c44df898d-cmhdc",
                        "hostSimMachineId": 1183832,
                        "simMachineType": "CONTAINER"
                    },
                    "_features": {
                        "features": [
                            "basic",
                            "sim"
                        ]
                    },
                    "_machineInstanceRegistrationRequestConfig": {
                        "forceMachineInstanceRegistration": true
                    }
                }
            },
            "controllerConfig": {
                "rawConfig": {
                    "_agentRegistrationRequestConfig": {
                        "agentVersion": "4.5.16.0",
                        "autoRegisterAgent": true,
                        "installDirectory": "",
                        "jvmInfo": "",
                        "machineInfo": "os.name=linux|os.arch=amd64|os.version=unknown"
                    },
                    "_agentRegistrationSupplementalConfig": {
                        "containerType": "APM",
                        "historical": false,
                        "hostName": "catqa3livelsi-app-5c44df898d-cmhdc",
                        "hostSimMachineId": 1183832,
                        "simMachineType": "CONTAINER"
                    },
                    "_features": {
                        "features": [
                            "sim"
                        ],
                        "reason": {
                            "code": "",
                            "message": ""
                        }
                    },
                    "_machineInstanceRegistrationRequestConfig": {
                        "forceMachineInstanceRegistration": true
                    }
                }
            },
            "cpus": [],
            "dynamicMonitoringMode": "KPI",
            "hierarchy": [
                "Containers",
                "LSI"
            ],
            "historical": false,
            "hostId": "85af50289777",
            "id": 1222683,
            "memory": {},
            "name": "85af50289777",
            "networkInterfaces": [],
            "properties": {
                "AppDynamics|Machine Type": "NON_CONTAINER_MACHINE_AGENT",
                "Container|Created At": "2024-05-20T14:21:39Z",
                "Container|Hostname": "85af50289777",
                "Container|Id": "85af50289777",
                "Container|Image|Id": "040055090629.dkr.ecr.us-east-2.amazonaws.com/ecomm/commerce/lsi-app@sha256:6cdb04f2a52353536405facf04adf9fcd496f04b132de579378cd9e0b8cea7e4",
                "Container|Image|Name": "040055090629.dkr.ecr.us-east-2.amazonaws.com/ecomm/commerce/lsi-app:main_20240517.2",
                "Container|K8S|Namespace": "qa3",
                "Container|K8S|PodName": "catqa3livelsi-app-5c44df898d-cmhdc",
                "Container|Name": "lsi-app",
                "Container|Started At": "2024-05-20T14:21:48Z"
            },
            "simEnabled": true,
            "simNodeId": 95291051,
            "tags": {},
            "type": "CONTAINER",
            "volumes": []
        }
        '''

        namespace = podName = containerName = containerImage = containerCreated = containerStarted = ""
        machineInfo = server["agentConfig"]["rawConfig"]["_agentRegistrationRequestConfig"]["machineInfo"]
        agentVersion = server["agentConfig"]["rawConfig"]["_agentRegistrationRequestConfig"]["agentVersion"]

        if (server["type"] == "CONTAINER" and not server["historical"]):
            '''
            # use for debugging - outputs the server entity
            formatted_json = json.dumps(server, indent=4, sort_keys=True)
            print(formatted_json)
            input("Press any key to continue...")
            '''
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

            if ("Container|Created At" in server["properties"]):
                containerCreated = server["properties"]["Container|Created At"]
            else:
                print("The key 'Container|Created At' does not exist in the dictionary")

            if ("Container|Started At" in server["properties"]):
                containerStarted = server["properties"]["Container|Started At"]
            else:
                print("The key 'Container|Started At' does not exist in the dictionary")
                
        csv_writer.writerow([server["hierarchy"], server["hostId"], server["name"], namespace, podName, containerName, containerImage, containerCreated, containerStarted, server["tags"], server["memory"], server["volumes"], server["cpus"], machineInfo, agentVersion, server["simEnabled"], server["type"], server["dynamicMonitoringMode"], server["historical"]])