# This script requires you to create an API key in AppDynamics and add the account owner and administrator roles to it.
# you will need to replace the value below with the values related to the controller you would like to query
# and the API client name and secret. The script will look at the last year of data to determine the last time agents connected.
# If no availability metrics were registered in over 12 months for the tier, you will see OUT OF RANGE in the resulting CSV file.
# for questions / help contact Robert Vandervoort - rvander2@cisco.com
# CHEERS!

import json
import csv
import datetime
import urllib.parse
import requests

#--- CONFIGURATION SECTION ---

# print debug info set DEBUG to True if you need to get richer details about what is going on..
# will flood the console when running against a decent sized controller.
DEBUG = False

"""
Replace with your AppDynamics API client details
NOTE: When you set up the API client in your AppD controller's admin section you have the option
to choose how long the token is good for. If you have a large deployment and the script takes longer
than your token is valid for then you will start seeing unauthorized messages coming across the output on screen.
I ran this against one of my customers with nearly 21000 nodes and it took over an hour to complete. N
"""
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
Set this METRIC_DURATION_MINS variable to how far you want to look back in time to find the last time agents reported in. The value is in minutes.
Depending on how far you look back, data will be aggregated. If you go back 12 months, you'll get 1 hour data points.
Data is only retained for 13 months max. The father you go back the longer the script will take to run.
I would recommend for your first time running this you go back a year or since you deployed, whichever is less.
For subsequent runs, decrease the time considerably. Three examples follow. Ensure only one is uncommented.

Also, metric rollups should be considered when using broader time ranges see the doc:
https://docs.appdynamics.com/appd/24.x/latest/en/extend-appdynamics/appdynamics-apis/metric-and-snapshot-api#MetricandSnapshotAPI-DataRetentionforMetricandSnapshotAPI
"""

#How far back are we looking for data
#METRIC_DURATION_MINS = 525600 #12 months
#METRIC_ROLLUP = "true"

METRIC_DURATION_MINS = 43800 #1 month
METRIC_ROLLUP = "true"

#METRIC_DURATION_MINS = 1440 #1 day
#METRIC_ROLLUP = "true"

#METRIC_DURATION_MINS = 240 #4 hours
#METRIC_ROLLUP = "false"

#METRIC_DURATION_MINS = 5 #5 mins
#METRIC_ROLLUP = "false"

#---FUNCTION DEFINITIONS

def connect(account, apiclient, secret):
    """Connects to the AppDynamics API and retrieves an OAuth token."""

    global __session__ #make session headers with the token usable through the rest of the code
    __session__ = requests.Session()

    url = f"{BASE_URL}/controller/api/oauth/access_token?grant_type=client_credentials&client_id={apiclient}@{account}&client_secret={secret}"
    payload = {} # set empty because we're not sending a payload
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    print(f"Logging into the controller at: {BASE_URL}")

    try:
        response=__session__.request(
            "POST",
            url,
            headers=headers,
            data=payload,
            verify=VERIFY_SSL
        )
        response.raise_for_status()  # Raise an exception for any non-2xx status code

        json_response = response.json()

        if DEBUG:
            print("Session headers:", __session__.headers)
            print("Auth:", json_response['access_token'])

        __session__.headers['X-CSRF-TOKEN'] = json_response['access_token']
        __session__.headers['Authorization'] = f'Bearer {json_response["access_token"]}'

        print("Logged in!")
        return True

    except requests.exceptions.ConnectionError as connection_error:
        print(f"Connection error: {connection_error}")
        print("Check your controller URL and account then network connectivity and server status.")
    
    except requests.exceptions.HTTPError as http_error:
        print(f"HTTP error occurred: {http_error.args[0]} (status code: {http_error.response.status_code})")
        if http_error.response.status_code == 401:
            print("Unauthorized: Check credentials and access permissions.")
        elif http_error.response.status_code == 404:
            print("Endpoint not found: Verify the URL.")
            sys.exit(71)
        elif http_error.response.status_code == 500:
            print("Internal server error.")
            sys.exit(73)
        else:
            print("Please contact support for assistance.")
    
    except Exception as connect_exception:
        if DEBUG:
            raise # re-raise the exception
                  # traceback gets printed
        else:
            print(f"        --- {type(connect_exception).__name__}: {connect_exception}")

    sys.exit(1)

def urlencode_string(text):
    """make app, tier or node names URL compatible for the REST call"""
    # Replace spaces with '%20'
    text = text.replace(' ', '%20')

    # Encode the string using the 'safe' scheme
    safe_characters = '-_.!~*\'()[]+:;?,/=$&%'
    encoded_text = urllib.parse.quote(text, safe=safe_characters)

    return encoded_text

def get_metric(object_type, app, tier, agenttype, node):
    """fetches last known agent availability info from tier or node level."""
    tier = urlencode_string(tier)
    app = urlencode_string(app)

    if object_type == "node":
        if agenttype == "MACHINE_AGENT":
            metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CIndividual%20Nodes%7C" + node + "%7CAgent%7CMachine%7CAvailability"
        else:
            metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CIndividual%20Nodes%7C" + node + "%7CAgent%7CApp%7CAvailability"
    
    elif object_type == "tier":
        metric_path = "Application%20Infrastructure%20Performance%7C" + tier + "%7CAgent%7CApp%7CAvailability"
        
    # If the machine agents were assigned a tier, the tier reads as an app agent. The availability data would be here instead
    # metric_path = "Application%20Infrastructure%20Performance%7C" + tier_name + "%7CAgent%7CMachine%7CAvailability"
    # future enhancement will reflect the number and last seen for machine agent tiers.

    metric_url = BASE_URL + "/controller/rest/applications/" + app + "/metric-data?metric-path=" + metric_path + "&time-range-type=BEFORE_NOW&duration-in-mins=" + str(METRIC_DURATION_MINS) + "&rollup=" + METRIC_ROLLUP + "&output=json"
                                
    #get metric data
    if DEBUG:
        print("        --- metric url: " + metric_url)

    try:
        metric_response = requests.get(
            metric_url,
            headers = __session__.headers,
            verify = VERIFY_SSL
        )
        metric_response.raise_for_status()  # Raise an exception for any non-2xx status code

    except requests.exceptions.ConnectionError as connection_error:
        print(f"Connection error: {connection_error}")
        print("Check your controller URL and account then network connectivity and server status.")
    
    except requests.exceptions.HTTPError as http_error:
        print(f"HTTP error occurred: {http_error.args[0]} (status code: {http_error.response.status_code})")
        if http_error.response.status_code == 401:
            print("Unauthorized: Check credentials and access permissions.")
        elif http_error.response.status_code == 404:
            print("Endpoint not found: Verify the URL.")
            sys.exit(71)
        elif http_error.response.status_code == 500:
            print("Internal server error.")
            sys.exit(73)
        else:
            print("Please contact support for assistance.")
    
    except Exception as connect_exception:
        if DEBUG:
            raise # re-raise the exception
                  # traceback gets printed
        else:
            print(f"        --- {type(connect_exception).__name__}: {connect_exception}")

    metric_data = validate_json(metric_response)
    json_data, metric_status = metric_data

    if metric_status == "valid":
        if (json_data[-1]['metricName'] == "METRIC DATA NOT FOUND"):
            dt = "METRIC DATA NOT FOUND IN TIME RANGE"
            return dt, None
        
        else:
            last_start_time_millis = json_data[-1]['metricValues'][-1]['startTimeInMillis']
            #convert EPOCH to human readable datetime - we have to divide by 1000 because we show EPOCH in ms not seconds
            dt = datetime.datetime.fromtimestamp((last_start_time_millis/1000))

            #use max value for tier to prevent values not adding up due to wonky data
            if object_type == "tier":
                value = json_data[-1]['metricValues'][-1]['max']
            elif object_type == "node":
                value = json_data[-1]['metricValues'][-1]['value']

            return dt, value

    elif metric_status == "empty":
        dt = "EMPTY RESPONSE"
        if DEBUG:
            print(metric_response)
            #sys.exit()
        return dt, None
    
    elif metric_status == "error":
        dt = "ERROR IN JSON RESPONSE"
        return dt, None


def validate_json(data):
    """validation function to parse into JSON and catch empty sets returned from our API requests"""
    if not data:
        #this state is NOT always an error. Sometimes there are old tiers with no nodes anymore. Same for apps.
        if DEBUG:
            print("---- Response object contents that were judged empty ----------------------------")
            print(data.text)
        return None, "empty"

    try:
        # parse the request object into a json object 
        json_data = data.json()
        
        # check for empty JSON object
        if not json_data:
            if DEBUG:
                print("\n            ---- The resulting JSON object judged as empty")
                print(f"            ---- data.text {data.text} , json_data {json_data}")
            return None, "empty"

    except json.JSONDecodeError:
        # The data is not valid JSON.
        if DEBUG:
            print("The data is not valid JSON.")
        return None, "error"

    # The data is valid JSON.
    return json_data, "valid"

#--- MAIN
#get XCSRF token for use in this session
connect(APPDYNAMICS_ACCOUNT_NAME, APPDYNAMICS_API_CLIENT, APPDYNAMICS_API_CLIENT_SECRET)

# Get a list of all applications
if not application_id:
    APPLICATIONS_URL = BASE_URL + "/controller/rest/applications?output=json"
    print("--- Retrieving applications from "+APPLICATIONS_URL)

else:
    APPLICATION_URL = BASE_URL + "/controller/rest/applications/" + str(application_id) + "?output=json"
    print("--- Retrieving applications from "+APPLICATION_URL)

try:
    if application_id:
        applications_response = requests.get(
            APPLICATION_URL,
            headers = __session__.headers,
            verify = VERIFY_SSL
        )
    else:
        applications_response = requests.get(
            APPLICATIONS_URL,
            headers = __session__.headers,
            verify = VERIFY_SSL
        )
    applications_response.raise_for_status()  # Raise an exception for any non-2xx status code

    applications_data = validate_json(applications_response)
    applications, applications_status = applications_data

except requests.exceptions.ConnectionError as connection_error:
    print(f"Connection error: {connection_error}")
    print("Check your controller URL and account then network connectivity and server status.")

except requests.exceptions.HTTPError as http_error:
    print(f"HTTP error occurred: {http_error.args[0]} (status code: {http_error.response.status_code})")
    if http_error.response.status_code == 401:
        print("Unauthorized: Check credentials and access permissions.")
    elif http_error.response.status_code == 404:
        print("Endpoint not found: Verify the URL.")
        sys.exit(71)
    elif http_error.response.status_code == 500:
        print("Internal server error.")
        sys.exit(73)
    else:
        print("Please contact support for assistance.")

except Exception as connect_exception:
    if DEBUG:
        raise # re-raise the exception
                # traceback gets printed
    print(f"--- {type(connect_exception).__name__}: {connect_exception}")

if applications_status == "valid":
    # Open the output CSV file for writing and write the header row
    print("Writing to CSV file: " + OUTPUT_CSV_FILE)
    with open(OUTPUT_CSV_FILE, "w", newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["Application", "Description", "Tier", "agenttype", "Last up", "Last up count", "Node", "machineAgentVersion", "appAgentVersion"])

        # Iterate over each application and start the output
        print("Iterating over each application to fetch tier and node data...")
        for application in applications:
            application_id = application["id"]
            application_name = application["name"]
            application_description = application["description"]
            print(f"--- {application_name} : {application_id}")

            # Get a list of all tiers in the application
            TIERS_URL = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/tiers?output=json"
            
            if DEBUG:
                print("    --- Fetching tiers from: "+ TIERS_URL)
            
            try:
                tiers_response = requests.get(
                    TIERS_URL,
                    headers = __session__.headers,
                    verify = VERIFY_SSL
                )
                tiers_response.raise_for_status()  # Raise an exception for any non-2xx status code

                tiers_data = validate_json(tiers_response)
                tiers, tiers_status = tiers_data
            
            except requests.exceptions.ConnectionError as connection_error:
                print(f"Connection error: {connection_error}")
                print("Check your controller URL and account then network connectivity and server status.")
                tiers = {}
                tiers_status = "error"

            except requests.exceptions.HTTPError as http_error:
                print(f"HTTP error occurred: {http_error.args[0]} (status code: {http_error.response.status_code})")
                if http_error.response.status_code == 401:
                    print("Unauthorized: Check credentials and access permissions.")
                elif http_error.response.status_code == 404:
                    print("Endpoint not found: Verify the URL.")
                    sys.exit(71)
                elif http_error.response.status_code == 500:
                    print("Internal server error.")
                    sys.exit(73)
                else:
                    print("Please contact support for assistance.")
                
                tiers = {} # Set to an empty dictionary in case of errors
                tiers_status = "error"

            except Exception as connect_exception:
                if DEBUG:
                    raise # re-raise the exception
                            # traceback gets printed
                print(f"--- {type(connect_exception).__name__}: {connect_exception}")
                
                tiers = {} # Set to an empty dictionary in case of errors
                tiers_status = "error"

            if tiers_status == "error":
                csv_writer.writerow([application_name, application_description, "AN ERROR OCCURRED RETRIEVING TIERS", "", "", "", "", "", ""])
                continue # do not stop processing through tiers because of an error pulling its tiers
            
            if tiers_status == "empty":
                csv_writer.writerow([application_name, application_description, "NO TIERS FOUND", "", "", "", "", "", ""])
                continue # do not stop processing through applications because they do not have tiers

            if (tiers_status == "valid"):
                # Iterate over each tier in the application
                for tier in tiers:
                    tier_name = tier["name"]
                    tier_id = tier["id"]
                    tier_type = tier["type"]
                    tier_agent_type = tier["agentType"]
                    if DEBUG:
                        print(f"    --- tier name:{tier_name}, tier id: {tier_id} type:{tier_type}, agenttype:{tier_agent_type}")
                    else:
                        print(f"    --- tier: {tier_name}")
                    
                    #grab tier availability data
                    print("        --- Querying tier availability.")
                    availability_values = get_metric("tier", application_name, tier_name, tier_agent_type, "null")
                    dt, value = availability_values
                    
                    if value:
                        print(f"        --- Tier last seen on {str(dt)} - {str(value)} nodes seen.")
                        if WRITE_TIER_AVAILABILITY_DATA:    
                            csv_writer.writerow([application_name, application_description, tier_name, tier_agent_type, dt, value, "-", "-", "-"])
                    else:
                        print(f"        --- Metric data not returned, message: {str(dt)}")
                        if WRITE_TIER_AVAILABILITY_DATA:    
                            csv_writer.writerow([application_name, application_description, tier_name, tier_agent_type, dt, value, "-", "-", "-"])
                    
                    # Get a list of all nodes for the tier
                    nodes_url = BASE_URL + "/controller/rest/applications/" + str(application_id) + "/tiers/" + str(tier_id) + "/nodes?output=json"
                    if DEBUG:
                        print(f"        --- Fetching node data from {nodes_url}.")
                    else:
                        print("        --- Fetching nodes from tier.")

                    try:
                        nodes_response = requests.get(
                            nodes_url,
                            headers = __session__.headers,
                            verify = VERIFY_SSL
                        )
                        nodes_response.raise_for_status()  # Raise an exception for non-200 status codes

                        nodes_data = validate_json(nodes_response)
                        nodes, nodes_status = nodes_data

                    except requests.exceptions.ConnectionError as connection_error:
                        print(f"Connection error: {connection_error}")
                        print("Check your controller URL and account then network connectivity and server status.")
                        nodes = {} # Set to an empty dictionary in case of errors
                        nodes_status = "error"

                    except requests.exceptions.HTTPError as http_error:
                        print(f"HTTP error occurred: {http_error.args[0]} (status code: {http_error.response.status_code})")
                        if http_error.response.status_code == 401:
                            print("Unauthorized: Check credentials and access permissions.")
                        elif http_error.response.status_code == 404:
                            print("Endpoint not found: Verify the URL.")
                            sys.exit(71)
                        elif http_error.response.status_code == 500:
                            print("Internal server error.")
                            sys.exit(73)
                        else:
                            print(f"HTTP Error response: {http_error.response.status_code} - Please contact support for assistance.")
                        
                        nodes = {} # Set to an empty dictionary in case of errors
                        nodes_status = "error"

                    except Exception as connect_exception:
                        if DEBUG:
                            raise # re-raise the exception
                                    # traceback gets printed
                        print(f"        --- {type(connect_exception).__name__}: {connect_exception}")
                        
                        nodes = {} # Set to an empty dictionary in case of errors
                        nodes_status = "error"
                    
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
                                print(f"        --- node name:{node_name}, node id: {node_id} type:{node_type}, agenttype:{node_agent_type}")
                            else:
                                print(f"        --- {node_name}")

                            print(f"        --- Querying node availability.")
                            
                            availability_values = get_metric("node", application_name, tier_name, node_agent_type, node_name)
                            dt, value = availability_values
                            
                            if value:
                                print(f"        --- Node last seen on {str(dt)}")
                                csv_writer.writerow([application_name, application_description, tier_name, node_agent_type, dt, value, node_name, node_machineAgentVersion, node_appAgentVersion])

                            else:
                                print(f"        --- Metric data not returned, message: {dt}")
                                csv_writer.writerow([application_name, application_description, tier_name, node_agent_type, dt, "", node_name, node_machineAgentVersion, node_appAgentVersion])                   

else:
    print(f"No applications returned. Status: {applications_status}")
    sys.exit(1)