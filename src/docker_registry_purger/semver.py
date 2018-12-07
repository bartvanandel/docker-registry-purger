import daiquiri
import re

from .timestamp import find_timestamp


logger = daiquiri.getLogger(__name__)


SEMVER_REGEX = re.compile(r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<prerelease>.+))?$')


class Semver:
    def __init__(self, major, minor, patch, prerelease):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease

        # Try to find timestamp
        timestamp = None
        if prerelease:
            timestamp = find_timestamp(prerelease)

        self.timestamp = timestamp

    def parse(tag):
        if tag:
            match = SEMVER_REGEX.match(tag)

            if match:
                return Semver(
                    int(match.group('major')),
                    int(match.group('minor')),
                    int(match.group('patch')),
                    match.group('prerelease'))

        return None

    def __str__(self):
        pre = f'-{self.prerelease}' if self.prerelease else ''
        return f'{self.major}.{self.minor}.{self.patch}{pre}'


def parse_semver(tag):
    return Semver.parse(tag)
