# class Veracross: code adapted from https://github.com/beckf/veracross_api/
import parse
import requests
import time
import sys
import os

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parents[1]  # /app
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv, find_dotenv

project_root = Path(__file__).resolve().parents[1]  # /app
load_dotenv(project_root / ".env")

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

def find_any_id_by_item(data, item_to_find, to_find, to_return):
    """
    Look through one or more 'users' containers to find a user where
    user[item_to_find] == to_find, and return user[to_return].

    Works with:
      - data: dict with key 'users' -> list[dict]
      - data: list[dict], each with key 'users' -> list[dict]

    Returns:
      The value of user[to_return] from the first match, or None if not found.
    """
    # Normalize input to a list of dict containers
    if isinstance(data, dict):
        containers = [data]
    elif isinstance(data, list):
        containers = [d for d in data if isinstance(d, dict)]
    else:
        return None

    for container in containers:
        users = container.get('users') or []
        for user in users:
            if isinstance(user, dict) and user.get(item_to_find) == to_find:
                return user.get(to_return)

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

def filter_pairs(flat_list, banned=("Study Hall", "DEAR", "Lunch", "Help", "Advisory")):
    """
    flat_list: [id1, name1, id2, name2, ...]
    returns a new flat list with banned name pairs removed
    """
    out = []
    it = iter(flat_list)
    for id_val, name in zip(it, it):  # step through in pairs
        name_str = str(name).strip()
        if any(bad.lower() in name_str.lower() for bad in banned):
            continue  # skip this pair
        out.extend([id_val, name])
    return out

