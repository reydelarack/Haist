#!/usr/bin/env python
import requests
import urllib3
import json
import sys
import getpass
import paramiko
import time
import os

def jprint(jsondoc):
    print json.dumps(jsondoc, sort_keys=True, indent=2, separators=(',', ': '))

requests.packages.urllib3.disable_warnings()

logo = """\
                             _________
                           ______________
                        ___________________
                    __________________   _____
                _________  __________   _______
             __________  ____  _____   _________
           ___________  ___     ___  ____________
         ____________  ___     ___  _____________
       _____________   __     __   _______________
     ______________    _______    ________________
    ______________      ___      _________________
   ______________               __________________ HAIST
  ______________                _________________
 ______________                __________________  High
 _____________                 _________________  Altitude
______________     ______      ________________  Intercontinental
_____________    __________    _______________  Server
_____________   ____________    _____________  Transmitter
____________   ______________   ____________
____________   _______________  __________
 __________   ________________   _______
  _________   _________________  _____
   ________  ______________________
    _______  __________________
     _____   ____________
         __
"""

print(logo)

print("")
'''
Get information from user to auth against identity.
'''
username = raw_input('Enter Rackspace username: ')
password = getpass.getpass('Enter Password or API Key: ')

regions = ['iad', 'ord', 'dfw', 'syd', 'hkg', 'lon']

#Request to authenticate using password
def get_token(username,password):
    #setting up api call
    url = "https://identity.api.rackspacecloud.com/v2.0/tokens"
    headers = {'Content-type': 'application/json'}
    payload = {'auth':{'passwordCredentials':{'username': username,'password': password}}}
    payload2 = {'auth':{'RAX-KSKEY:apiKeyCredentials':{'username': username,'apiKey': password}}}

    #authenticating against the identity
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Connection Error: Check your interwebs!")
        sys.exit()

    if r.status_code != 200:
        r = requests.post(url, headers=headers, json=payload2)
        if r.status_code != 200:
            print("Invalid username / password / apiKey")
            sys.exit()
        else:
            print("Authentication was successful!")
    elif r.status_code == 200:
        print("Authentication was successful!")
    elif r.status_code == 400:
        print("Bad Request. Missing required parameters. This error also occurs if you include both the tenant name and ID in the request.")
        sys.exit()
    elif r.status_code == 401:
        print("Unauthorized. This error message might indicate any of the following conditions:")
        print("    -You are not authorized to complete this operation.")
        print("    -Additional authentication credentials required. Submit a second authentication request with multi-factor authentication credentials")
        sys.exit()
    elif r.status_code == 403:
        print("User disabled Forbidden")
    elif r.status_code == 404:
        print("Item not found. The requested resource was not found. The subject token in X-Subject-Token has expired or is no longer available. Use the POST token request to get a new token.")
        sys.exit()
    elif r.status_code == 500:
        print("Service Fault. Service is not available")
        sys.exit()
    else:
        print("Unknown Authentication Error")
        sys.exit()

    #loads json reponse into data as a dictionary.
    data = r.json()
    #assign token and account variables with info from json response.
    token = data["access"]["token"]["id"]
    account = data["access"]["token"]["tenant"]["id"]
#needed to detect RCv3 Cloud Identity Role
    all_roles=data["access"]["user"]["roles"]
    #
    return token,account,all_roles

token,account,all_roles = get_token(username,password)

print(token)

print("")

#Begin RCv3 compatibility changes

def check_for_rackconnect(all_roles, account):
# first we check for the RackConnect API role.
    # first we check for the RackConnect API role.
    for role in range (len(all_roles)):
        rackconnect_role_check=all_roles[role]["name"]
#This logic catches accounts with the RCv3 cloud load balancers role as well
        rackconnect_regions=[]

        if "rackconnect" and "v3" in rackconnect_role_check:
            rackconnect_regions.append(all_roles[role]["name"].lower().split("-")[1])
            break
            return rackconnect_regions

        elif "RCv3" and "SG" in rackconnect_role_check:
            print rackconnect_role_check
            rackconnect_regions.append(all_roles[role]["name"].lower().split("-")[0].split(":")[1])
            break
            return rackconnect_regions



    #if we've gotten this far, then the account does not have rackconnect
    return rackconnect_regions

def find_rackconnect_network(token, account, rackconnect_region):
#we'll use the RackConnect v3 API, as it's the source of truth for RCv3 networks
    Header= {'content-type': 'application/json', 'Accept': 'application/json', 'X-Auth-Token': token}
    rackconnect_network_url = ("https://" + rackconnect_region +
    ".rackconnect.api.rackspacecloud.com/v3/" + account + "/cloud_networks")
    rackconnect_network_list = requests.get(rackconnect_network_url, headers=Header)
#For now, we just grab the UUID of the first RCv3 network. Later, we'll let you choose.
    rackconnect_network=rackconnect_network_list.json()[0]["id"]
    return rackconnect_network

rackconnect_regions=check_for_rackconnect(all_roles,account)

if not rackconnect_regions:
    rackconnect_network = 0
    rackconnect_region =  0
else:
    print ("""
           RackConnect v3 detected on account. At this time, the RCv3 region is
           only supported as the destination region.""")
    raw_input('Press Enter to accept this, or CTRL-C to quit: ')
    rackconnect_region = rackconnect_regions[0]
    rackconnect_network = find_rackconnect_network(token, account, rackconnect_region)

src_srvr = raw_input('Enter Source Server UUID: ')
BFV = False
def get_src_details():
    headers = {"X-Auth-Token": token}
    src_image = "null"
    for i in range(len(regions)):
        region = (regions[i])
        url = "https://" + region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + src_srvr
        try:
            r = requests.get(url,headers=headers, stream=True)
        except requests.ConnectionError as e:
            print("Can't connect to server, please try again or check your internet")
            sys.exit()
        if r.status_code == 200:
            print "Found instance in " + region + "!"
            data = r.json()
            src_name = (data["server"]["name"])
            src_status = (data["server"]["status"])
            src_ip = (data["server"]["accessIPv4"])
            src_flavor = (data["server"]["flavor"]["id"])
            if (data["server"]["image"]) == "":
                global BFV
                BFV = True
                print("")
                print("Checking server's \"boot from volume\" details")
            if BFV != True:
                src_image = (data["server"]["image"]["id"])
            break
        else:
            print "Searching..." + region
            sys.stdout.write("\033[F") # Cursor up one line
            continue

    return src_name,src_status,src_ip,src_flavor,region,src_image

src_name,src_status,src_ip,src_flavor,src_region,src_image = get_src_details()


def check_src_disk():
    headers = {"X-Auth-Token": token}
    url = "https://" + src_region + ".servers.api.rackspacecloud.com/v2/" + account + "/flavors/" + str(src_flavor)

    try:
        r = requests.get(url,headers=headers,stream=True)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()['flavor']
        src_disk = data['disk']
        return src_disk


def check_src_volume():
    headers = {"X-Auth-Token": token}
    url = "https://" + src_region + ".blockstorage.api.rackspacecloud.com/v1/" + account + "/volumes/detail"

    try:
        r = requests.get(url,headers=headers,stream=True)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        vol_list = r.json()['volumes']
        vol_found = False

    for volume in vol_list:
        attachments = volume['attachments']
        for attachment in attachments:
            if attachment['server_id'] == src_srvr and attachment['device'] == "/dev/xvda" or "/dev/hda":
                vol_found = True
                src_vol_id = attachment['volume_id']
                src_vol_size = volume['size']
                src_image = volume['volume_image_metadata']['image_id']

            else:
                print("Server's root disk could not be found.")
                sys.exit()

    return src_vol_id,src_vol_size,src_image

if BFV:
    src_vol_id,src_vol_size,src_image = check_src_volume()
    print("Boot from volume server detected!")
    print "Found source server's boot volume which is " + str(src_vol_size) + "GB."
else:
    src_disk = check_src_disk()
    print("Source server's disk size is " + str(src_disk) + "GB.")


src_vm_mode = "null"
os_type = "null"

def check_src_image(src_vm_mode,os_type):
    headers = {"X-Auth-Token": token}
    url = "https://" + src_region + ".images.api.rackspacecloud.com/v2/" + account + "/images/" + src_image
    try:
        r = requests.get(url,headers=headers, stream=True)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()
    else:
        print("There was a problem checking the source server's image.")
        sys.exit()
    try:
        src_vm_mode = (data["vm_mode"])
    except KeyError:
        try:
            os_type = (data["os_type"])
        except KeyError:
            src_vm_mode = str.lower(raw_input("Can't detect source server's vm_mode, is it xen or hvm?: "))

    if src_vm_mode == "hvm":
        src_vm_mode = "hvm"
    elif src_vm_mode == "xen":
        src_vm_mode = "xen"
    elif os_type == "windows":
        os_type = "windows"
        src_vm_mode = "hvm"
    elif os_type != "windows" and src_vm_mode != "hvm":
        src_vm_mode = "xen"
    else:
        src_vm_mode = raw_input("Can't detect source server's vm_mode or os_type, is it xen or hvm?: ")
    return src_vm_mode,os_type

src_vm_mode,os_type = check_src_image(src_vm_mode,os_type)

#Get destination details from user
def set_dst_region():
    while True:
        dst_region = str.lower(raw_input('Enter the region where this server will be copied to, i.e. dfw, ord, iad: '))
        for i in range(len(regions)):
            if dst_region == (regions[i]):
                dst_region_bool = True
                return dst_region
                break
            else:
                dst_region_bool = False
        if dst_region_bool == False:
            print("You entered an invalid region abbreviation, please try again!")
            print("Possible regions are as follows...")
            for i in range(len(regions)):
                print (regions[i])

dst_region = set_dst_region()

def get_dst_image():
    if src_vm_mode == "hvm" and os_type != "windows":
        dst_image_name = "Ubuntu%2014.04%20LTS%20(Trusty%20Tahr)%20(PVHVM)"
    elif src_vm_mode == "xen":
        dst_image_name = "Ubuntu%2014.04%20LTS%20(Trusty%20Tahr)%20(PV)"
    elif os_type == "windows":
        dst_image_name = "Windows%20Server%202012%20R2"
    else:
        pass

    headers = {"X-Auth-Token": token}
    url = "https://" + dst_region + ".images.api.rackspacecloud.com/v2/" + account + "/images?name=" + dst_image_name
    try:
        r = requests.get(url,headers=headers, stream=True)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
    if r.status_code == 200:
        data = r.json()
        dst_image = (data["images"][0]["id"])
#        print "Found image to build destination skeleton server in " + dst_region + " (Image UUID: " + dst_image + ")"
        return dst_image
    else:
        print("There was a problem searching for the destination server's skeleton image")
        print("Enter the UUID of the base image your source server was created from.")
        dst_image = raw_input('Enter UUID: ')
        return dst_image

dst_image = get_dst_image()

print("")
print("IMPORTANT! At this time, the destination server must have the same size system disk or larger.")

def set_dst_flavor(question, default="no"):
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")

set_dst_flavor = set_dst_flavor('Yes to keep the same size and flavor. No to choose a different size or flavor', None)

if set_dst_flavor:
    dst_flavor = src_flavor

#set destination flavor variable based on set_dst_flavor bool
valid_vol = False
if set_dst_flavor == True and BFV == False:
    print "The destination server will be built as the " + src_flavor + " flavor."
    dst_flavor = src_flavor
elif set_dst_flavor and BFV:
    print("")
    while valid_vol == False:
        print "The destination volume must be the same or larger than " + str(src_vol_size) + "GB. Please enter the desired volume size."
        get_dst_vol_size = raw_input('Size for destination volume: ')
        if int(get_dst_vol_size) >= int(src_vol_size):
            dst_vol_size = get_dst_vol_size
            valid_vol = True
        else:
            print "You must enter a volume size greater than or equal to " + str(src_vol_size) + "GB!"
else:
    print "Please see https://www.rackspace.com/cloud/servers for a breakdown of flavors."
    dst_flavor = str.lower(raw_input('Please enter a valid flavor: '))


def check_dst_flavor(dst_flavor):
    headers = {"X-Auth-Token": token}
    valid_flavor = False
    while valid_flavor == False:
        try:
            url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/flavors/" + str(dst_flavor)
            r = requests.get(url,headers=headers,stream=True)
        except requests.ConnectionError as e:
            print("Can't connect to server, please try again or check your internet")
            sys.exit()
        if r.status_code == 200:
            data = r.json()['flavor']
            dst_disk = data['disk']
            return dst_disk,dst_flavor
            valid_flavor = True
        else:
            print "The flavor you have input is invalid, please try again."
            dst_flavor = str.lower(raw_input('Please enter a valid flavor: '))


dst_disk,dst_flavor = check_dst_flavor(dst_flavor)

'''
If source and selected destination are NOT BFV
check src_disk VS. dst_disk size for issues.
'''

if int(dst_disk) == 0:
    dst_BFV = True
else:
    dst_BFV = False

if BFV == False and dst_BFV == False:
    valid_dst_flavor = False
    dst_BFV = False
    while valid_dst_flavor == False:
        if int(dst_disk) >= int(src_disk):
            print("Valid destination flavor selected.")
            valid_dst_flavor = True
        else:
            print "You must enter a destination flavor whose disk is the same size or larger than the source disk."
            print "Your source " + src_flavor + " has a " + str(src_disk) + "GB. disk, while your " + str(dst_flavor) + " has a " + str(dst_disk) + "GB. disk."
            dst_flavor = str.lower(raw_input('Please enter a valid flavor: '))
            dst_disk,dst_flavor = check_dst_flavor(dst_flavor)
            if int(dst_disk) == 0:
                print "Now you'd like to boot from volume? Please enter a volume size greater than " + str(src_disk) + "GB."
                while dst_BFV == False:
                    dst_vol_size = raw_input('Volume size: ')
                    if int(dst_vol_size) >= int(src_disk):
                        valid_dst_flavor = True
                        dst_BFV = True
                        valid_vol = True
                    else:
                        print "Please enter a valid volume size larger than or equal to " + str(src_disk) + "GB."
            else:
                if int(dst_disk) >= int(src_disk):
                    print("Valid destination flavor selected.")
                    valid_dst_flavor = True
                else:
                    print "The destination disk is still too small..."
                    while valid_dst_flavor == False:
                        print "Your source " + src_flavor + " has a " + str(src_disk) + "GB. disk, while your " + str(dst_flavor) + " has a " + str(dst_disk) + "GB. disk."
                        dst_flavor = str.lower(raw_input('Please enter a valid flavor: '))
                        dst_disk,dst_flavor = check_dst_flavor(dst_flavor)
                        if int(dst_disk) >= int(src_disk):
                            valid_dst_flavor = True
                        else:
                            pass

#If selected dst_flavor is BFV now, set bool to True.

if int(dst_disk) == 0:
    dst_BFV = True
else:
    dst_BFV = False

'''
This next loop is for destination BFV only, and is being used to get a valid
destination volume size whether src is BFV or not.
'''

if valid_vol == False and dst_BFV == True:
    while valid_vol == False:
        if BFV == False:
            if int(src_disk) < 50:
                print "The destination volume must be the same or larger than 50GB. Please enter the desired volume size."
                get_dst_vol_size = raw_input('Size for destination volume: ')
                if int(get_dst_vol_size) >= 50:
                    dst_vol_size = get_dst_vol_size
                    valid_vol = True
                else:
                    print "You must enter a volume size greater than or equal to 50GB!"
            if int(src_disk) > 50:
                print "The destination volume must be the same or larger than " + str(src_disk) + "GB. Please enter the desired volume size."
                get_dst_vol_size = raw_input('Size for destination volume: ')
                if int(get_dst_vol_size) >= int(src_disk):
                    dst_vol_size = get_dst_vol_size
                    valid_vol = True
                else:
                    print "You must enter a volume size greater than or equal to " + str(src_disk) + "GB!"
        else:
            print "The destination volume must be the same or larger than " + str(src_vol_size) + "GB. Please enter the desired volume size."
            get_dst_vol_size = raw_input('Size for destination volume: ')
            if int(get_dst_vol_size) >= int(src_vol_size):
                dst_vol_size = get_dst_vol_size
                valid_vol = True
            else:
                print "You must enter a volume size greater than or equal to " + str(src_vol_size) + "GB!"


dst_name = raw_input('Enter a name for the destination server: ')

#payload if dst is BFV
#payload = {'server':{'name': str(dst_name),'flavorRef': dst_flavor,'block_device_mapping_v2':[{'boot_index': '0','uuid': dst_image,'volume_size': dst_vol_size,'source_type': 'image','destination_type': 'volume'}]}}

def build_dst_srvr(token, rackconnect_region,rackconnect_network):
#embedded function for RCv3, as we can't add public IP until Compute
#build is done.
    def check_server_progress(token, dst_srvs_url, dst_srvr):
        Header= {'content-type': 'application/json', 'Accept': 'application/json', 'X-Auth-Token': token}
        server_timer=0
        while True:
            server_url=dst_srvs_url + "/" + dst_srvr
            server_check=requests.get(url=server_url,headers=Header)
            server_status=server_check.json()["server"]["status"]
            if server_status != "BUILD":
                return server_status
                break
            time.sleep(30)
            print("""
                  "Step 1 of 3: RackConnect cloud server is in %s status. Checking again
                  in 30 seconds"
                  """) % server_status
            server_timer=server_timer + 1
            if server_timer >= 120:
                print "Server build took more than an hour. Giving up!"
                sys.exit()

    def get_rcv3_pub_ip(token, rackconnect_region, dst_srvr, server_status):
        Header= {'content-type': 'application/json', 'Accept': 'application/json', 'X-Auth-Token': token}
        rcv3_pub_ip_payload={
        "cloud_server": {
            "id": dst_srvr
                        }
                }
        rcv3_pub_ip_url = ("https://" + rackconnect_region +
        ".rackconnect.api.rackspacecloud.com/v3/" + account +  "/public_ips")
        if server_status != "ACTIVE":
            print "Server is not in active state, exiting"
    #This is the API call to provision a public IP. It doesn't have the public
    #IP in the response, just a UUID associated with the pubIP.
        print "Step 2 of 3: Build complete. Requesting new RackConnect public IP"
        rcv3_pub_ip_req=requests.post(url=rcv3_pub_ip_url, data=json.dumps(rcv3_pub_ip_payload), headers=Header)
        rcv3_pub_ip_id=rcv3_pub_ip_req.json()["id"]
        rcv3_provisioned_pub_ip_url = rcv3_pub_ip_url + "/" + rcv3_pub_ip_id
        rcv3_provision_ip_timer=0
        while True:
            rcv3_provision_ip_check=requests.get(url=rcv3_provisioned_pub_ip_url,headers=Header)
            rcv3_provision_ip_status=rcv3_provision_ip_check.json()["status"]
    #Extremely basic error handling for problems adding a public IP
            if rcv3_provision_ip_status == "ACTIVE":
                new_rcv3_pub_ip=rcv3_provision_ip_check.json()["public_ip_v4"]
                print("""Step 3 of 3: Receiving RackConnect public IP.
                       RackConnect Public IP is %s. Go to Firewall Manager in
                       the myrackspace.com portal and open TCP port 22 access
                       from source server IP and control server IP, to this IP.
                       (Yes, this is needed even for Windows servers).
                       """) % new_rcv3_pub_ip
                raw_input('Press enter when firewall rules are set.')
                return new_rcv3_pub_ip
                break
            time.sleep(30)
            rcv3_provision_ip_timer=rcv3_provision_ip_timer + 1
            print rcv3_provision_ip_status, rcv3_provision_ip_timer
            if rcv3_provision_ip_timer >= 4:
                print "It took more than 2 minutes to provision a public IP! Exiting!"
#begin main body of build_dst_srvr function
    if dst_BFV and not rackconnect_region:
        payload = {
            'server':{'name': str(dst_name),
                      'flavorRef': dst_flavor,
                      'block_device_mapping_v2':[{
                          'boot_index': '0',
                          'uuid': dst_image,
                          'volume_size': dst_vol_size,
                          'source_type': 'image',
                          'destination_type': 'volume'}]}}

    elif not dst_BFV and not rackconnect_region:
        payload = {
            'server':{'name': str(dst_name),
                      'imageRef': dst_image,
                      'flavorRef': dst_flavor}}
    elif dst_BFV and rackconnect_region:
        payload = {
            'server':{'name': str(dst_name),
                      'flavorRef': dst_flavor,
                      'block_device_mapping_v2':[{
                          'boot_index': '0',
                          'uuid': dst_image,
                          'volume_size': dst_vol_size,
                          'source_type': 'image',
                          'destination_type': 'volume'}],
                      	  'networks': [{
                              'uuid': rackconnect_network
                      		}, {
                      			'uuid': '11111111-1111-1111-1111-111111111111'
                      		}],
                      		"metadata": {
                      			"build_config": "monitoring_defaults"
                      		}
                      }}
    elif not dst_BFV and rackconnect_region:
        payload = {
                'server':{'name': str(dst_name),
                          'flavorRef': dst_flavor,
                          'imageRef': dst_image,
                          	  'networks': [{
                                  'uuid': rackconnect_network
                          		}, {
                          			'uuid': '11111111-1111-1111-1111-111111111111'
                          		}],
                          		"metadata": {
                          			"build_config": "monitoring_defaults"
                          		}
                          }}
    Header= {'content-type': 'application/json', 'Accept': 'application/json',
             'X-Auth-Token': token}
    dst_srvs_url = ("https://" + dst_region + ".servers.api.rackspacecloud.com/v2/"
                + account + "/servers")

    try:
        r = requests.post(url=dst_srvs_url, headers=Header, json=payload)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
    if r.status_code == 202:
        data = r.json()
        dst_srvr_pass = (data["server"]["adminPass"])
        global dst_srvr
        dst_srvr = (data["server"]["id"])
        if rackconnect_region:
                server_status = check_server_progress(token, dst_srvs_url, dst_srvr)
                rackconnect_pub_ip = get_rcv3_pub_ip(token, rackconnect_region, dst_srvr, server_status)
                print "RackConnect public IP is %s" % rackconnect_pub_ip

        return dst_srvr_pass

    else:
        print("There was a problem requesting the server to be built.")
        print r.status_code
        sys.exit()

dst_srvr_pass = build_dst_srvr(token, rackconnect_region, rackconnect_network)

print("")
print "Destination server build request accepted, server is building. (New Server UUID: " + dst_srvr + ")"

def get_src_rescue_image():
    headers = {"X-Auth-Token": token}
    url = "https://" + src_region + ".images.api.rackspacecloud.com/v2/" + account + "/images?name=Ubuntu+14.04+LTS+%28Trusty+Tahr%29+%28PVHVM%29"
    try:
        r = requests.get(url,headers=headers, stream=True)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()
        src_rescue_image = (data["images"][0]["id"])
        return src_rescue_image
    else:
        print("There was a problem obtaining the rescue image UUID")
        sys.exit()

print("")
print "Placing source server into rescue mode for transfer operations! (Source IP: " + src_ip + ")"

src_rescue_image = get_src_rescue_image()

def src_enter_rescue():
    payload = {"rescue": {"rescue_image_ref": src_rescue_image}}
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    url = "https://" + src_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + src_srvr + "/action"
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()
        src_rescue_pass = (data["adminPass"])
        return src_rescue_pass
    else:
        print("There was a problem requesting the server to be placed into rescue mode")
        sys.exit()

src_rescue_pass = src_enter_rescue()

print src_name + " is entering rescue mode, the temporary root password is: " + src_rescue_pass

def src_poll_status():
        headers = {"X-Auth-Token": token}
        url = "https://" + src_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + src_srvr
        try:
            r = requests.get(url,headers=headers, stream=True)
        except requests.ConnectionError as e:
            print("Can't connect to server, trying again....")
        if r.status_code == 200:
            data = r.json()
            src_rescue_status = (data["server"]["status"])
            return src_rescue_status

while src_poll_status() == "ACTIVE":
    for x in range (0,100):
        print ("Rescuing" + "." * x)
        sys.stdout.write("\033[F")
        time.sleep(5)
        if src_poll_status() == "RESCUE":
            break

print("Source server has entered rescue mode successfully!")

def dst_poll_status():
        headers = {"X-Auth-Token": token}
        url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr
        try:
            r = requests.get(url,headers=headers, stream=True)
        except requests.ConnectionError as e:
            print("Can't connect to server, trying again....")
        if r.status_code == 200:
            data = r.json()
            dst_status = (data["server"]["status"])
            global dst_ip
            dst_ip = (data["server"]["accessIPv4"])
            return dst_status

print("")

while dst_poll_status() != "ACTIVE":
    for x in range (0,100):
        print ("Destination server still building" + "." * x)
        sys.stdout.write("\033[F")
        time.sleep(7)
        if dst_poll_status() == "ACTIVE":
            break

print "The destination server finished building before source entered rescue mode! (Destination IP: " + str(dst_ip) + ")"
print("Placing destination server into rescue mode for transfer operations.")

def get_dst_rescue_image():
    headers = {"X-Auth-Token": token}
    url = "https://" + dst_region + ".images.api.rackspacecloud.com/v2/" + account + "/images?name=Ubuntu+14.04+LTS+%28Trusty+Tahr%29+%28PVHVM%29"
    try:
        r = requests.get(url,headers=headers, stream=True)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()
        dst_rescue_image = (data["images"][0]["id"])
        return dst_rescue_image
    else:
        print("There was a problem obtaining the rescue image UUID")
        sys.exit()

dst_rescue_image = get_dst_rescue_image()

def dst_enter_rescue():
    payload = {"rescue": {"rescue_image_ref": dst_rescue_image}}
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr + "/action"
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()
        dst_rescue_pass = (data["adminPass"])
        return dst_rescue_pass
    else:
        print("There was a problem requesting the server to be placed into rescue mode")
        sys.exit()

time.sleep(5)
dst_rescue_pass = dst_enter_rescue()

print "The destination instance is entering rescue mode, the temporary root password is: " + dst_rescue_pass

def dst_rescue_status():
        headers = {"X-Auth-Token": token}
        url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr
        try:
            r = requests.get(url,headers=headers, stream=True)
        except requests.ConnectionError as e:
            print("Can't connect to server, trying again....")
        if r.status_code == 200:
            data = r.json()
            dst_rescue_status = (data["server"]["status"])
            return dst_rescue_status

while dst_rescue_status() == "ACTIVE":
    for x in range (0,100):
        print ("Rescuing" + "." * x)
        sys.stdout.write("\033[F")
        time.sleep(5)
        if dst_rescue_status() == "RESCUE":
            break
print("Destination server has entered rescue mode successfully!")
print("")
print("Preparing to log into source server...")

time.sleep(6)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(str(src_ip), username='root', password=str(src_rescue_pass))

print("Generating public/private rsa key pair for filesystem transmission.")
stdin, stdout, stderr = ssh.exec_command('ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa')
type(stdin)
stdout.readlines()
stderr.readlines()

print("")
print("Scanning destination server for host keys")
time.sleep(1)
stdin, stdout, stderr = ssh.exec_command('ssh-keyscan ' + str(dst_ip)\
 + ' >> ~/.ssh/known_hosts')
type(stdin)
for line in stdout.readlines():
    print line,
for line in  stderr.readlines():
    print line,

print("")
print("Updating source server's package lists.")
stdin, stdout, stderr = ssh.exec_command('apt-get update')
type(stdin)
stdout.readlines()
stderr.readlines()
time.sleep(1)
stdin, stdout, stderr = ssh.exec_command('apt-get install sshpass -y')
type(stdin)
stdout.readlines()
stderr.readlines()
time.sleep(1)
print("")
print("Installing temporary public rsa key on destination rescue instance.")
stdin, stdout, stderr = ssh.exec_command("sshpass -p " + str(dst_rescue_pass) + " ssh-copy-id\
 root@" + str(dst_ip))
type(stdin)
stdout.readlines()
stderr.readlines()

#Set TCP congestion algorithm for faster xfer
stdin, stdout, stderr = ssh.exec_command('sysctl net.ipv4.tcp_congestion_control=illinois &&\
 ssh root@' + str(dst_ip) + ' \"sysctl net.ipv4.tcp_congestion_control=illinois\"')
type(stdin)
stdout.readlines()
stderr.readlines()

stdin, stdout, stderr = ssh.exec_command("echo \"logfile flush 1\" >> /etc/screenrc")
type(stdin)
for line in stdout.readlines():
    print line,
for line in  stderr.readlines():
    print line,

#We have to wipe out the partition table on destination,
#otherwise Windows servers won't migrate properly

print ("")
print ("Zeroing out the partition table on destination in preparation for copy")
stdin, stdout, stderr = ssh.exec_command("screen -LdmS HAIST bash -c \'ssh root@"\
+ str(dst_ip) + "dd if=/dev/zero of=/dev/xvdb bs=512 count=2\"; exec bash\'")


#Copying the disk via DD

stdin, stdout, stderr = ssh.exec_command("screen -LdmS HAIST bash -c \'dd if=/dev/xvdb conv=sync,noerror,sparse bs=64K | gzip -c | ssh root@" + str(dst_ip) + " \"gunzip -c | dd of=/dev/xvdb\"; exec bash\'")
type(stdin)
for line in stdout.readlines():
    print line,
for line in  stderr.readlines():
    print line,

time.sleep(3)

print("")
print("Initializing transfer!")
stdin, stdout, stderr = ssh.exec_command("screen -dmS PROGRESS bash -c \'watch -n 2 \"kill -USR1 $(pgrep ^dd) && sleep .5 && tail -n 1 screenlog.* > haist_progress\"; exec bash\'")
type(stdin)
for line in stdout.readlines():
    print line,
for line in  stderr.readlines():
    print line,

time.sleep(2)

counter = 0
progress = None
prevprogress = None
loopvar = True

while loopvar:
    stdin, stdout, stderr = ssh.exec_command('cat haist_progress')
    type(stdin)
    for line in stdout.readlines():
        print(line)
        sys.stdout.write("\033[F")
        sys.stdout.write("\033[F")
        prevprogress = progress
        progress = line
    time.sleep(3)
    if progress is not None and progress == prevprogress:
        counter = counter + 1
        if counter == 6:
            loopvar = False
    else:
        time.sleep(3)
        counter = - 1
        if counter == -3:
            counter = 0

print("")
print("The source server's file system has been cloned to the destination server's disk!")
print("")
print("Taking servers out of rescue mode now, Standby.")
time.sleep(5)

bye_dst_rescue = False
def dst_leave_rescue():
    payload = {"unrescue": 'null'}
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr + "/action"
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 202:
        bye_dst_rescue = True
        return bye_dst_rescue
    else:
        print("There was a problem requesting the server to leave rescue mode")
        sys.exit()

bye_dst_rescue = dst_leave_rescue()

bye_src_rescue = False
def src_leave_rescue():
    payload = {"unrescue": 'null'}
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    url = "https://" + src_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + src_srvr + "/action"
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 202:
        bye_src_rescue = True
        return bye_src_rescue
    else:
        print("There was a problem requesting the server to leave rescue mode")
        sys.exit()

bye_src_rescue = src_leave_rescue()

pollvar = True

reset_network = False

def status_chk(pollvar,reset_network):
    while pollvar:
        for x in range (0,100):
            print ("Un-Rescuing" + "." * x)
            sys.stdout.write("\033[F")
            headers = {"X-Auth-Token": token}
            dst_url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr
            src_url = "https://" + src_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + src_srvr

            try:
                dst_r = requests.get(dst_url,headers=headers, stream=True)
            except requests.ConnectionError as e:
                print("Can't connect to server, trying again....")
            if dst_r.status_code == 200:
                dstdata = dst_r.json()
                dst_rescue_status = (dstdata["server"]["status"])

            try:
                src_r = requests.get(src_url,headers=headers, stream=True)
            except requests.ConnectionError as e:
                print("Can't connect to server, trying again....")
            if src_r.status_code == 200:
                srcdata = src_r.json()
                src_rescue_status = (srcdata["server"]["status"])

            if dst_rescue_status == "ACTIVE":
                reset_network = True
                return reset_network
            if dst_rescue_status and src_rescue_status == "ACTIVE":
                print("Both servers have exited rescue mode, and are powering on.")
                print("")
                pollvar = False
                if dst_rescue_status == "ERROR":
                    print("The destination server has entered an error state, please investigate.")
                if src_rescue_status == "ERROR":
                    print("The source server has entered an error state, please investigate.")
                if dst_rescue_status or src_rescue_status == "ERROR":
                    pollvar = False
                time.sleep(3)

if bye_src_rescue and bye_dst_rescue == True:
    print("Unrescue call has been accepted for both servers.")
    reset_network = status_chk(pollvar,reset_network)
else:
    raw_input('Please verify servers are unrescuing, then hit enter: ')
    reset_network = status_chk(pollvar,reset_network)

dst_reset = False
def reset_dst_net(reset_network,dst_reset):
    if reset_network == True:
        payload = {"resetNetwork": 'null'}
        headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
        url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr + "/action"
        for x in range (0,120):
            print ("Attempting network reset on destination server in " + str(120 - x) + " seconds.")
            sys.stdout.write("\033[F")
            time.sleep(1)
        try:
            r = requests.post(url, headers=headers, json=payload)
        except requests.ConnectionError as e:
            print("Can't connect to server, please try again or check your internet")
            sys.exit()
        if r.status_code == 202:
            dst_reset = True
            return dst_reset
        else:
            print("There was a problem requesting the server to be placed into rescue mode")
            sys.exit()

dst_reset = reset_dst_net(reset_network,dst_reset)
print("")
if dst_reset == True:
    for x in range (0,15):
        print ("The reset network request has been sent, resetting..." + str(15 - x))
        sys.stdout.write("\033[F")
        time.sleep(1)
    print("")
    print("Checking network connectivity to " + str(dst_name))
    dst_icmp = os.system("ping -c 10 " + dst_ip + " > /dev/null 2>&1")
    if dst_icmp == 0:
        print(str(dst_name) + " is responding to icmp.")
        os.system("ping -c 4 " + dst_ip)
    else:
        print(str(dst_name) + " is not responding to ICMP requests.")

print("")

dst_console = None
def get_dst_console(dst_console):
    payload = {'os-getVNCConsole': {'type': 'novnc'}}
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    url = "https://" + dst_region + ".servers.api.rackspacecloud.com/v2/" + account + "/servers/" + dst_srvr + "/action"
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Can't connect to server, please try again or check your internet")
        sys.exit()
    if r.status_code == 200:
        data = r.json()['console']
        dst_console = (data["url"])
        return dst_console
    else:
        print("While trying to get a novnc console URL for " + str(dst_name) + ", got a " + str(r.status_code)) + " status code."

dst_console = get_dst_console(dst_console)

if dst_console is not None:
    print("If you'd like to investigate the destination server via console, here is a novnc (HTML5) console link.")
    print(dst_console)

print("")

end_of_prog = False
while end_of_prog == False:
    raw_input('You have reached the end of the program, press enter to exit.')
    end_of_prog = True
    sys.exit
