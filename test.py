# class Veracross: code adapted from https://github.com/beckf/veracross_api/

import parse
import requests
import time
import sys
import os
import json

from tabulate import tabulate

sys.path.append('../..')

from dotenv import load_dotenv, find_dotenv

_ = load_dotenv(find_dotenv())  # read local .env file

credentials = os.environ['school'], os.environ['client_id'], os.environ['secret']

class Veracross:
    def __init__(self, config):
        self.bearer_token = None
        self.school = config["school"]
        self.token_url = f"https://accounts.veracross.com/{self.school}/oauth/token"
        self.oneroster_token_url = f"https://accounts.veracross.com/{self.school}/oauth/oneroster"
        self.api_base_url = f"https://api.veracross.com/{self.school}/v3/"
        self.oneroster_base_url = f"https://oneroster.veracross.com/{self.school}/ims/oneroster/v1p1/"
        self.client_id = config["client_id"]
        self.client_secret = config["client_secret"]
        self.scopes = config["scopes"]
        # Requests Session
        self.session = requests.Session()
              # Rate limit defaults
        self.rate_limit_remaining = 300
        self.rate_limit_reset = 0
        # Default page size
        self.page_size = 500

        # Session Headers
        self.session.headers.update({'Accept': 'application/json',
                                     'X-Page-Size': str(self.page_size)
                                     })
              # DEBUG Logs
        # When set, dump a bunch of info
        self.debug = False
    def __repr__(self):
        if self.bearer_token:
            return f"Veracross_API3 connected to {self.api_base_url}"
        else:
            return "Veracross_API3"

    def debug_log(self, text):
        """
        If debug enabled - print stuff
        :param text:
        :return:
        """
        if self.debug:
            print(text)

    def get_authorization_token(self):
        """
        Get / refresh bearer token from veracross api.
        :return: string: bearer token
        """
        s = requests.Session()

        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials',
                'scope': ' '.join(self.scopes)
            }
            r = s.post(self.token_url, data=payload, headers=headers)
            json = r.json()

            self.bearer_token = json["access_token"]
            self.session.headers.update({'Authorization': 'Bearer ' + self.bearer_token})

            self.debug_log(f"Bearer token: {self.bearer_token}")

            return json["access_token"]
        except Exception as e:
            print(e)

    def check_rate_limit(self, headers):
        if "X-Rate-Limit-Remaining" in headers:
            self.rate_limit_remaining = int(headers["X-Rate-Limit-Remaining"])

            now = int(time.time())
            reset = int(headers["X-Rate-Limit-Reset"])
            wait = reset - now
            self.rate_limit_reset = int(wait)

            if int(headers["X-Rate-Limit-Remaining"]) < 2:
                self.debug_log("VC rate limit reached. Waiting {} seconds.".format(wait))
                time.sleep(wait)

            self.debug_log(f"X-Rate-Limit-Remaining Header: {headers['X-Rate-Limit-Remaining']}")
            self.debug_log(f"X-Rate-Limit-Reset Header: {headers['X-Rate-Limit-Reset']}")
            self.debug_log(f"This rate limit value: {self.rate_limit_remaining}")

        else:
            return False

    def pull(self, oneORnot, endpoint, parameters=None):
        """
        Pull requested data from veracross api.
        :return: data
        """
        self.get_authorization_token()

        if oneORnot != "oneRoster":
            if parameters:
                url = self.api_base_url + endpoint + "?" + parse.urlencode(parameters, safe=':-')
            else:
                url = self.api_base_url + endpoint
        else:
            url = self.oneroster_base_url + endpoint

        self.debug_log(f"V-Pull URL: {url}")

        # Get first page
        page = 1
        r = self.session.get(url)

        self.debug_log(f"V-Pull HTTP Headers: {r.headers}")
        self.debug_log(f"V-Pull HTTP Status Code: {r.status_code}")

        if r.status_code == 401:
            # Possible a scope is missing
            self.debug_log(f"V-Pull 401: Missing Scope?")
            self.debug_log(r.text)
            return None

        if r.status_code == 200:
            self.check_rate_limit(headers=r.headers)
            data = r.json()
            if oneORnot != "oneRoster":
                data = data['data']
            last_count = len(data)
            self.debug_log("V-Pull data length page 1: {}".format(len(data)))
        else:
            return None

        # Any other pages to get?
        while last_count >= self.page_size:
            page += 1
            r = self.session.get(url,
                                 headers={'X-Page-Number': str(page)})

            self.debug_log("V-Pull Page Number: {}".format(page))
            self.debug_log(f"V-Pull HTTP Headers: {r.headers}")
            self.debug_log(f"V-Pull HTTP Status Code: {r.status_code}")

            # Handle 401
            if r.status_code == 401:
                # Possible a scope is missing
                self.debug_log(f"V-Pull 401: Missing Scope?")
                self.debug_log(r.text)
                return None

            if r.status_code == 200:
                self.check_rate_limit(headers=r.headers)
                next_page = r.json()
                last_count = len(next_page['data'])
                data = data + next_page['data']

                self.debug_log("V-Pull data length: {}".format(len(data)))

        return data

def find_any_id_by_item(data_dict, item_to_find, to_find, to_return):
    """
    Searches the 'users' list in the data dictionary for a specific email
    and returns the corresponding 'sourcedId'.
    """
    # Access the list of users, defaulting to an empty list if 'users' key is missing
    user_list = data_dict.get('users', [])

    # Iterate through each user dictionary in the list
    for user in user_list:
        # Check if the 'email' field matches the email we're looking for
        # Using .get('email') is safer as it returns None if 'email' key doesn't exist
        if user.get(item_to_find) == to_find:
            # If it matches, return the 'sourcedId'
            # .get('sourcedId') is also safer
            return user.get(to_return)

    # If the loop finishes without finding the email, return None
    return None


def find_all_matches(data_dict, list_item, to_return, item_to_find=None, comparison=None):
    """
    Searches a list in the dictionary and returns a *list* of values.

    - If item_to_find/comparison are provided, it filters for all matches.
    - If not, it gets the value from all items in the list.

    Returns an empty list [] if no matches are found.
    """
    results_list = []
    item_list = data_dict.get(list_item, [])

    # Check if we are in "filtering" mode
    is_filtering = item_to_find is not None and comparison is not None

    for item in item_list:
        if is_filtering:
            # Filter mode: Only add if it matches the comparison
            if item.get(item_to_find) == comparison:
                results_list.append(item.get(to_return))
        else:
            # "Get all" mode: Add the value from every item
            results_list.append(item.get(to_return))

    # This handles Case 3 (no matches) by returning an empty list
    return results_list

# Code starts here :)
c = {
    "school": credentials[0],
    "client_id": credentials[1],
    "client_secret": credentials[2],
    "scopes": ['https://purl.imsglobal.org/spec/or/v1p1/scope/roster-core.readonly','https://purl.imsglobal.org/spec/or/v1p1/scope/roster.readonly','classes:list', 'academics.classes:list', 'academics.classes:read', 'academics.enrollments:list', 'academics.enrollments:read', 'classes:read', 'report_card.enrollments.qualitative_grades:list']
}

student_email = input("Please enter the student email address: ")

endpointOne = "students"
endpointTwo = "classes"
vc = Veracross(c)

# Pulling student data into the student_list.json file
# Veracross returns 100 max files - must call it 3 times
student_list =[]
num = 100
update_students = input("Do you want to update the student list? (y/n): ")
if update_students.lower() == "y":
    student_list.append(vc.pull("oneRoster", endpointOne))
    student_list.append(vc.pull("oneRoster", endpointOne + "?offset=" + str(num)))
    student_list.append(vc.pull("oneRoster", endpointOne + "?offset=" + str(num+100)))
    with open("student_list.json", "w") as outfile:
        outfile.seek(0)
        outfile.truncate()
        json.dump(student_list, outfile)

with open("student_list.json", "r") as infile:
    student_list = json.load(infile)

# Stripping down the list to iterate through it more easily
student_list = student_list[0]
sourcedId = find_any_id_by_item(student_list, 'email', student_email, 'sourcedId')




# Pull a list of students via OneRoster
# data = vc.pull("oneRoster", endpointOne)
# print("TOTAL ITEMS:", endpointOne, len(data["users"]))

# Return the sourcedId for the requested student
sourcedId = None
while sourcedId is None:
    sourcedId = find_any_id_by_item(student_list, 'email', student_email, 'sourcedId')
    if sourcedId is None:
        print("Email address is not found.")
        student_email = input("Please enter the student email address again: ")



# Iterate through the GET since it only pulls 100 records at a time
"""num = 100
while sourcedId is None:
    data = vc.pull("oneRoster", endpointOne + "?offset=" + str(num))
    print("TOTAL ITEMS:", endpointOne, num)
    sourcedId = find_any_id_by_item(data, 'email', student_email, 'sourcedId')
    num += 100
    if num > 300:
        print("Email address is not found.")
        student_email = input("Please enter the student email address again: ")
        num = 0"""

# Pull class data for the student from OneRoster
endpointThree = "students/" + sourcedId + "/classes"
classes_data = vc.pull("oneRoster", endpointThree)

# Extract all veracrossId's from the data
veracrossId = find_all_matches(classes_data, "classes", "classCode")

endpointFour = "students/"+sourcedId
student_data = vc.pull("oneRoster", endpointFour)

# Extract identifier which is the Veracross student ID number
studentId = student_data.get('user',{}).get('identifier', 'Not found')
print(studentId)

# Pull the enrollment data for the student using Veracross ID.
# This gives us the enrollment ids which we need for grade reports.
endpointFive = "academics/enrollments"
enrollments_data = vc.pull("non", endpointFive + "?person_id=" + studentId)

# Extracts enrollments Ids and class descriptions separate lists.
class_descriptions = []
enrollment_ids = []
for item in enrollments_data:
    enrollment_ids.append(item.get('id'))
    class_descriptions.append(item.get('class_description'))

# Pulls qualitative report card data and adds class descriptions to the lists
# Counts down through the classes as it pulls data from each one
qualitative_data = []
for i in range(0, len(enrollment_ids)):
    endpointSix = "report_card/enrollments/" + str(enrollment_ids[i]) + "/qualitative_grades"
    qd = vc.pull("non",endpointSix)
    qualitative_data.append(qd)
    qualitative_data.append(class_descriptions[i])
    print(len(enrollment_ids) - i, end=" ")
print()

# Create an empty list to hold the processed data
processed_data = []

# Iterate through the main list using an index
# This allows us to look at the next item
for i in range(len(qualitative_data)):
    current_item = qualitative_data[i]

    # Check if the current item is a list (which might contain dicts)
    if isinstance(current_item, list):

        # The class name is the next item in the list
        class_name = None
        if (i + 1) < len(qualitative_data) and isinstance(qualitative_data[i + 1], str):
            class_name = qualitative_data[i + 1]

        # Iterate through the dictionaries in this list
        for item in current_item:
            # We must check if 'item' is a dictionary,
            # because the list could be empty (like at the start)
            if isinstance(item, dict):
                # Safely get the proficiency level abbreviation
                abbreviation = item.get('proficiency_level', {}).get('abbreviation')

                # Check if the abbreviation is NOT None (the filter)
                if abbreviation is not None:
                    # If it's not None, extract the required information
                    gp_abbr = item.get('grading_period', {}).get('abbreviation')
                    rc_desc = item.get('rubric_criteria', {}).get('description')

                    # Create a new dictionary with the extracted data
                    extracted_item = {
                        'class': class_name,  # The new field
                        'grading_period': gp_abbr,
                        'description': rc_desc,
                        'score': abbreviation
                    }

                    # Add this new dictionary to our processed list
                    processed_data.append(extracted_item)

# Creates the table with alignment for numeric columns and a different style
table = tabulate(processed_data,headers = "keys", tablefmt="pipe",colalign=("left", "center", "right"))

# Prints the table
print(table)
