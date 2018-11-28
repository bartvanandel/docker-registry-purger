import datetime
import re


# We support only one time stamp format which includes date and time.
# Example: "20181128T161823"
TIMESTAMP_LENGTH = 15
TIMESTAMP_FORMAT = '%Y%m%dT%H%M%S'
TIMESTAMP_REGEX = re.compile(r'^(?P<timestamp>\d{8}T\d{6})$', re.IGNORECASE)
TIMESTAMP_SUBSTRING_REGEX = re.compile(r'(?:\b|_)(?P<timestamp>\d{8}T\d{6})(?:\b|_)', re.IGNORECASE)


def find_timestamp(string):
    match = TIMESTAMP_SUBSTRING_REGEX.search(string)

    if match:
        return as_timestamp(match.group('timestamp'))
    else:
        return None

def as_timestamp(string):
    if len(string) != TIMESTAMP_LENGTH:
        return None
    try:
        # NB: alternatively there is isodate.parse_datetime(string),
        #     however this is way too liberal in its excepted formats
        return datetime.datetime.strptime(string.upper(), TIMESTAMP_FORMAT).date()
    except ValueError as e:
        return None