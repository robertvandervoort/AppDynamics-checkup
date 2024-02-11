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
import urllib.parse
import requests


#--- CONFIGURATION SECTION ---

# print debug info set DEBUG to True if you need to get RICH details about what is going on..
# will flood the console when running against a decent sized controller.
DEBUG = False

#Replace with your AppDynamics API client details
APPDYNAMICS_ACCOUNT_NAME = ""
APPDYNAMICS_API_CLIENT = ""
APPDYNAMICS_API_CLIENT_SECRET = ""

#For reporting on a single application use the ID from the query seen in the URL in AppD,
application_id = "" # leave this as is and do not comment it out


# Now off by default - setting this to True will write a row in the output CSV representing the number of app nodes seen on a tier and the last time that tier availability was seen. 
# Initially this was useful ro help create this script but now it kind of just confuses the data so we are not grabbing it by default.
WRITE_TIER_AVAILABILITY_DATA = False

# Replace with the desired output CSV file path and name or leave as it to create dynamically (recommended)
#OUTPUT_CSV_FILE = "output.csv"
OUTPUT_CSV_FILE = APPDYNAMICS_ACCOUNT_NAME+"_checkup_"+datetime.date.today().strftime("%m-%d-%Y")+".csv"

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

#---FUNCTION DEFINITIONS
def connect(account, apiclient, secret):
    """Connects to the AppDynamics API and retrieves an OAuth token."""

    global __session__  
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
    else:
        print(f"Unable to log in at: {BASE_URL}")
        print("Please check your controller URL and try again.")
        sys.exit(9)

    if DEBUG:
        print("Session headers:", __session__.headers)
        print("Auth:", json_response['access_token'])

    __session__.headers['X-CSRF-TOKEN'] = json_response['access_token']
    __session__.headers['Authorization'] = f'Bearer {json_response["access_token"]}'
    print("Logged in!")
    return True 

def authenticate():
    #get XCSRF token for use in this session
    connect(APPDYNAMICS_ACCOUNT_NAME, APPDYNAMICS_API_CLIENT, APPDYNAMICS_API_CLIENT_SECRET)
    return

def handle_rest_errors(func):
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
            #try authetication up to x times if we get a 401
            if error_code == "401":
                while x > 0:
                    x = 3
                    authenticate()
                    x = x-1
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
        print(f"        --- Querying node availability.")
        if agenttype == "MACHINE_AGENT":
            metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CIndividual%20Nodes%7C" + node + "%7CAgent%7CMachine%7CAvailability"
        else:
            metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CIndividual%20Nodes%7C" + node + "%7CAgent%7CApp%7CAvailability"
    
    elif object_type == "tier":
        print(f"        --- Querying tier availability.")
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
    #Processes returned metric JSON data
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
    # Get a list of all applications
    print("--- Fetching applications...")

    if application_id:
        #chosen when user supplied an app id in the config
        APPLICATIONS_URL = BASE_URL + "/controller/rest/applications/" + str(application_id) + "?output=json"
        if DEBUG:
            print("--- from "+APPLICATIONS_URL)
    else:
        APPLICATIONS_URL = BASE_URL + "/controller/rest/applications?output=json"
        if DEBUG:
            print("--- from "+APPLICATIONS_URL)
    
    applications_response = requests.get(
        APPLICATIONS_URL,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )

    if DEBUG:
        print(applications_response.text)
    return applications_response

@handle_rest_errors
def get_tiers(application_id):
    # Gets the tiers in the application
    TIERS_URL = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/tiers?output=json"
    
    if DEBUG:
        print("    --- Fetching tiers from: "+ TIERS_URL)
    else:
        print("    --- Fetching tiers...")

    tiers_response = requests.get(
        TIERS_URL,
        headers = __session__.headers,
        verify = VERIFY_SSL
    )
    if DEBUG:
        print(f"    --- get_tiers response: {tiers_response.text}")

    return tiers_response

@handle_rest_errors
def get_nodes(application_id, tier_id):
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

#--- MAIN
authenticate()

#Get applications
applications_response = get_applications()
#Validate response
applications, applications_status = validate_json(applications_response)

if applications_status == "valid":
    # Open the output CSV file for writing and write the header row
    print("Writing to CSV file: " + OUTPUT_CSV_FILE)
    with open(OUTPUT_CSV_FILE, "w", newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["Application", "Description", "Tier", "agenttype", "Last up", "Last up count", "Node", "machineAgentVersion", "appAgentVersion"])

        # Iterate over each application and start the output
        for application in applications:
            application_id = application["id"]
            application_name = application["name"]
            application_description = application["description"]
            print(f"--- {application_name} : {application_id}")

            #retrieve tiers for the app
            tiers_response = get_tiers(application_id)
            #validate response
            tiers, tiers_status = validate_json(tiers_response)
            
            if tiers_status == "error":
                csv_writer.writerow([application_name, application_description, "AN ERROR OCCURRED RETRIEVING TIERS", "", "", "", "", "", ""])
                continue # do not stop processing through tiers because of an error pulling its tiers
            
            if tiers_status == "empty":
                csv_writer.writerow([application_name, application_description, "NO TIERS FOUND", "", "", "", "", "", ""])
                continue # do not stop processing through applications because they do not have tiers

            if (tiers_status == "valid"):
                if tiers == []:
                    csv_writer.writerow([application_name, application_description, "NO TIERS FOUND", "", "", "", "", "", ""])
                    continue # do not stop processing through applications because they do not have tiers

                # Iterate over each tier in the application
                for tier in tiers:
                    tier_name = tier["name"]
                    tier_id = tier["id"]
                    tier_type = tier["type"]
                    tier_agent_type = tier["agentType"]
                    tier_node_count = tier["numberOfNodes"]
                    #if DEBUG:
                    #    print(f"    --- tier name:{tier_name}, tier id: {tier_id} number of nodes: {tier_node_count} type:{tier_type}, agenttype:{tier_agent_type}")
                    #else:
                    print(f"    --- tier: {tier_name}")
                    
                    #get tier availability data
                    availability_response = get_metric("tier", application_name, tier_name, tier_agent_type, "null")
                    #validate the response                
                    availability_data, availability_data_status = validate_json(availability_response)
                    dt, value = handle_metric_response(availability_data, availability_data_status)
                    
                    if value:
                        print(f"        --- Tier last seen on {str(dt)} - {str(value)} nodes seen.")
                        if WRITE_TIER_AVAILABILITY_DATA:    
                            csv_writer.writerow([application_name, application_description, tier_name, tier_agent_type, dt, tier_node_count, "-", "-", "-"])
                    else:
                        print(f"        --- Metric data not returned, message: {str(dt)}")
                        if WRITE_TIER_AVAILABILITY_DATA:    
                            csv_writer.writerow([application_name, application_description, tier_name, tier_agent_type, dt, value, "-", "-", "-"])
                    
                    # Get a list of all nodes for the tier
                    nodes_response = get_nodes(application_id, tier_id)
                    #validate response
                    nodes_data = validate_json(nodes_response)
                    nodes, nodes_status = nodes_data

                    #write an appropriate line if nodes are not found - rare
                    if nodes_status == "empty":
                        print("        --- NO NODES FOUND!")
                        csv_writer.writerow([application_name, application_description, tier_name, "", "", "", "No nodes returned", "", ""])
                        continue # do not stop processing through tiers because the tier is empty - consider deleting the tier...

                    #write an appropriate line if there was an error retrieving nodes
                    elif nodes_status == "error":
                        csv_writer.writerow([application_name, application_description, tier_name, "", "", "", "ERROR retrieving nodes", "", ""])
                        continue # do not stop processing through tiers because of an error pulling its nodes
                            
                    # Iterate over each node in the tier and write to the CSV
                    elif nodes_status == "valid":
                        for node in nodes:
                            node_id = node["id"]
                            node_name = node["name"]
                            node_machineAgentVersion = node["machineAgentVersion"]
                            node_appAgentVersion = node["appAgentVersion"]
                            node_agent_type = node["agentType"]
                            if DEBUG:
                                print(f"        --- Node name:{node_name}, node id: {node_id}, agenttype:{node_agent_type}")
                            else:
                                print(f"        --- {node_name}")
                                                        
                            #get node availability data
                            availability_response = get_metric("node", application_name, tier_name, node_agent_type, node_name)
                            availability_data, availability_data_status = validate_json(availability_response)
                            dt, value = handle_metric_response(availability_data, availability_data_status)
                            
                            if value:
                                print(f"        --- Node last seen on {str(dt)}")
                                csv_writer.writerow([application_name, application_description, tier_name, node_agent_type, dt, value, node_name, node_machineAgentVersion, node_appAgentVersion])

                            else:
                                print(f"        --- Metric data not returned, message: {dt}")
                                csv_writer.writerow([application_name, application_description, tier_name, node_agent_type, dt, "", node_name, node_machineAgentVersion, node_appAgentVersion])                   

else:
    print(f"No applications returned. Status: {applications_status}")
    sys.exit(1)