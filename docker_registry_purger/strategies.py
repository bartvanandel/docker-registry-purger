import abc
import daiquiri
import datetime

from .semver import Semver
from .timestamp import as_timestamp, find_timestamp


logger = daiquiri.getLogger(__name__)


UNDECIDED = (None, 'undecided')


class BaseStrategy(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def should_keep(self, item, purger):
        """
        Determines whether to keep (True) or delete (False) the specified item, followed by a reason.
        Should return None if this strategy cannot decide.
        """
        raise NotImplementedError()


class WhitelistStrategy(BaseStrategy):
    def __init__(self, keep_latest=True, filename=None, string=None):
        super(WhitelistStrategy, self).__init__()

        self.repos = []
        self.tags = []
        self.repotags = []

        if keep_latest:
            self.tags.append('latest')
        if filename:
            self.load_file(filename)
        if string:
            self.load_string(string)

    def load_file(self, filename):
        try:
            with open(filename, 'r') as file:
                self.load_string(file.readlines())
        except EnvironmentError as ex: # parent of IOError, OSError *and* WindowsError where available
            raise ex

        return self

    def load_string(self, string):
        try:
            repos, tags, repotags = self.parse_whitelist(string)
            self.repos.extend(repos)
            self.tags.extend(tags)
            self.repotags.extend(repotags)
        except Exception as ex:
            raise ex

        return self

    def parse_whitelist(self, lines):
        """
        Parses a whitelist file, which should be a text file with one repo:tag per line.
        Empty and commented lines are skipped.
        Note: anywhere a tag is used, a digest can be used as well.

        Keep specific tag for one repository:
            some/repository:tag

        Keep entire repository:
            some/repository:*

        Keep tag:
            *:tag

        Keep everything (not very useful):
            *:*

        Comments are allowed, and should start with '#':
            # some comment
            some/repository:tag  # keep because bla bla
        """

        repos = []
        tags = []
        repotags = []
        for raw_line in lines:
            # Remove comment
            try:
                line, comment = raw_line.split('#', 1)
            except ValueError:
                line = raw_line

            line = line.strip()

            if line:
                parts = list(map(lambda s: s.strip(), line.split(':')))

                if len(parts) != 2:
                    raise ValueError(f'Error parsing whitelist line: {raw_line}')

                repo, tag = parts

                if not repo:
                    raise ValueError(f'Invalid repository in whitelist line: {raw_line}')

                if not tag:
                    raise ValueError(f'Invalid tag or digest in whitelist line: {raw_line}')

                if repo == '*':
                    if tag == '*':
                        raise ValueError(f'Invalid whitelist line: {raw_line}')
                    else:
                        tags.append(tag)
                elif tag == '*':
                    repos.append(repo)
                else:
                    repotags.append((repo, tag))

        return repos, tags, repotags

    def should_keep(self, item, purger):
        if item.repo in self.repos:
            return True, 'whitelisted by repository wildcard'
        elif item.tag in self.tags or item.digest in self.tags:
            return True, 'whitelisted by tag wildcard'
        else:
            for repo, tag in self.repotags:
                if item.repo == repo and (item.tag == tag or item.digest == tag):
                    return True, 'whitelisted'

        return UNDECIDED


class SemverStrategy(BaseStrategy):
    def __init__(self, max_age_major=None, max_age_minor=None, max_age_patch=None, max_age_prerelease=90, trust_timestamp_tags=True, require_semver=False):
        super(SemverStrategy, self).__init__()

        self.max_age_major = max_age_major
        self.max_age_minor = max_age_minor
        self.max_age_patch = max_age_patch
        self.max_age_prerelease = max_age_prerelease

        self.trust_timestamp_tags = trust_timestamp_tags
        self.require_semver = require_semver

    def should_keep(self, item, purger):
        semver = Semver.parse(item.tag)

        if semver:
            item.semver = semver

            age = -1

            if self.trust_timestamp_tags and semver.timestamp:
                age = (datetime.date.today() - semver.timestamp).days
                item.age = age

                return age < self.max_age_prerelease, 'age based on timestamp in semver tag'
            else:
                if (semver.prerelease and self.max_age_prerelease) or (self.max_age_major or self.max_age_minor or self.max_age_patch):
                    logger.info('Retrieving metadata for %s:%s', item.repo, item.tag)
                    age, digest = purger.registry.get_age(item.repo, item.tag)
                    if age:
                        item.age = age
                    if digest:
                        item.digest = digest

                    # For the moment, only look at prereleases
                    if semver.prerelease:
                        return age < self.max_age_prerelease, 'age based on metadata'

            # Semver but young enough to keep
            return True, 'keep semver non-prerelease by default'

        # Not a semver
        if self.require_semver:
            return False, 'not a semver'
        else:
            return UNDECIDED


class TimestampTagStrategy(BaseStrategy):
    def __init__(self, max_age=90, whole_tag_only=False):
        super(TimestampTagStrategy, self).__init__()

        self.max_age = max_age
        self.whole_tag_only = whole_tag_only

    def should_keep(self, item, purger):
        if self.whole_tag_only:
            timestamp = as_timestamp(item.tag)
        else:
            timestamp = find_timestamp(item.tag)

        if timestamp:
            item.timestamp = timestamp
            age = (datetime.date.today() - timestamp).days
            item.age = age

            return age < self.max_age, 'age based on timestamp in tag'

        return UNDECIDED
