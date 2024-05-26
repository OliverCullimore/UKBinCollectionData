import ssl
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup

from uk_bin_collection.uk_bin_collection.common import *
from uk_bin_collection.uk_bin_collection.get_bin_data import AbstractGetBinDataClass


class CustomHttpAdapter(requests.adapters.HTTPAdapter):
    """Transport adapter" that allows us to use custom ssl_context."""

    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=self.ssl_context,
        )

# import the wonderful Beautiful Soup and the URL grabber
class CouncilClass(AbstractGetBinDataClass):
    """
    Concrete classes have to implement all abstract operations of the
    base class. They can also override some operations with a default
    implementation.
    """

    def parse_data(self, page: str, **kwargs) -> dict:
        # Get and check UPRN
        user_uprn = kwargs.get("uprn")
        check_uprn(user_uprn)
        user_uprn = user_uprn.zfill(
            12
        )  # Expects a 12 character UPRN or else it falls over, expects 0 padded UPRNS at the start for any that aren't 12 chars

        user_postcode = kwargs.get("postcode")
        check_postcode(user_postcode)

        # Start a new session to walk through the form
        s = requests.Session()
        ssl_context = ssl.create_default_context()
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.options = ssl.PROTOCOL_TLS & ssl.OP_NO_TLSv1_3
        s.mount("https://", CustomHttpAdapter(ssl_context))
        requests.packages.urllib3.disable_warnings()

        # Get our initial session running
        response = s.get("https://secure.ashford.gov.uk/waste/collectiondaylookup/")

        soup = BeautifulSoup(response.text, features="html.parser")
        soup.prettify()

        # Grab the ASP variables needed to continue
        payload = {
            "ctl00$ScriptManager1": (
                "ctl00$UpdatePanel1|ctl00$ContentPlaceHolder1$CollectionDayLookup2$Button_PostCodeSearch"
            ),
            "__EVENTTARGET": (""),
            "__EVENTARGUMENT": (""),
            "__VIEWSTATE": (soup.find("input", {"id": "__VIEWSTATE"}).get("value")),
            "__VIEWSTATEGENERATOR": (
                soup.find("input", {"id": "__VIEWSTATEGENERATOR"}).get("value")
            ),
            "__EVENTVALIDATION": (
                soup.find("input", {"id": "__EVENTVALIDATION"}).get("value")
            ),
            "ctl00$ContentPlaceHolder1$CollectionDayLookup2$HiddenField_UPRN": (""),
            "ctl00$ContentPlaceHolder1$CollectionDayLookup2$TextBox_PostCode": (
                user_postcode
            ),
            "__ASYNCPOST": ("true"),
            "ctl00$ContentPlaceHolder1$CollectionDayLookup2$Button_PostCodeSearch": (
                "Please wait..."
            ),
        }

        # Use the above to get to the next page with address selection
        response = s.post(
            "https://secure.ashford.gov.uk/waste/collectiondaylookup/", payload
        )

        soup = BeautifulSoup(response.text, features="html.parser")
        soup.prettify()

        # Load the new variables that are constant and can't be gotten from the page
        payload = {
            "ctl00$ScriptManager1": (
                "ctl00$UpdatePanel1|ctl00$ContentPlaceHolder1$CollectionDayLookup2$Button_SelectAddress"
            ),
            "ctl00$ContentPlaceHolder1$CollectionDayLookup2$HiddenField_UPRN": (""),
            "ctl00$ContentPlaceHolder1$CollectionDayLookup2$DropDownList_Addresses": (
                user_uprn
            ),
            "__EVENTTARGET": (""),
            "__EVENTARGUMENT": (""),
            "__LASTFOCUS": (""),
            "__VIEWSTATE": (soup.find("input", {"id": "__VIEWSTATE"}).get("value")),
            "__VIEWSTATEGENERATOR": (
                soup.find("input", {"id": "__VIEWSTATEGENERATOR"}).get("value")
            ),
            "__EVENTVALIDATION": (
                soup.find("input", {"id": "__EVENTVALIDATION"}).get("value")
            ),
            "__ASYNCPOST": ("true"),
            "ctl00$ContentPlaceHolder1$CollectionDayLookup2$Button_SelectAddress": (
                "Please wait..."
            ),
        }

        # Get the final page with the actual dates
        response = s.post(
            "https://secure.ashford.gov.uk/waste/collectiondaylookup/", payload
        )

        soup = BeautifulSoup(response.text, features="html.parser")
        soup.prettify()

        data = {"bins": []}

        # Get the dates.
        for bin_type in ["Refuse", "Recycling", "FoodWaste"]:
            bin = soup.find("td", {"id": "ContentPlaceHolder1_CollectionDayLookup2_td_" + bin_type})
            if bin:
                bin_date_ref = bin_type
                if bin_date_ref != "FoodWaste":
                    bin_date_ref += "Waste"
                bin_date = bin.find("span", {"id": "ContentPlaceHolder1_CollectionDayLookup2_Label_" + bin_date_ref + "_Date"}).get_text(strip=True)
                if bin_date:
                    if bin_type == "FoodWaste":
                        bin_type = "Food Waste"
                    dict_data = {
                        "type": bin_type,
                        "collectionDate": datetime.strptime(
                            bin_date,
                            "%A %d/%m/%Y"
                        ).strftime(date_format),
                    }
                    data["bins"].append(dict_data)

        data["bins"].sort(
            key=lambda x: datetime.strptime(x.get("collectionDate"), date_format)
        )

        return data
