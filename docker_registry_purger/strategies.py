import abc
import daiquiri
import datetime
import re

from .semver import Semver
from .timestamp import as_timestamp, find_timestamp


logger = daiquiri.getLogger(__name__)


DIGEST_REGEX = re.compile(r'^(?:sha256:(?P<sha256>[0-9a-f]{64}))$')
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
        self.repo_tags = []
        self.digests = []
        self.repo_digests = []

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
            repos, tags, repo_tags, digests, repo_digests = self.parse_whitelist(string)
            self.repos.extend(repos)
            self.tags.extend(tags)
            self.repo_tags.extend(repo_tags)
            self.digests.extend(digests)
            self.repo_digests.extend(repo_digests)
        except Exception as ex:
            raise ex

        return self

    def parse_whitelist(self, lines):
        """
        Parses a whitelist file, which should be a text file with one
        repo:digest_or_tag pair per line. Empty and commented lines are skipped.
        Note that currently only sha256 digest is supported, and such values
        should contain the proper 'sha256:' prefix in the digest_or_tag part.
        For lines containing a digest, the repository is optional (because
        digests are unique anyway), but having the repository available will
        allow us to skip checking items for which the repository does not match.
        Also note that multiple tags may point to the same digest (i.e., blob).

        Keep specific digest or tag for one repository:
            some/repository:sha256:deafbeefdeadbeefdeafbeefdeadbeefdeafbeefdeadbeefdeafbeefdeadbeef
            some/repository:tag

        Keep entire repository:
            some/repository:*

        Keep digest or tag:
            *:sha256:deafbeefdeadbeefdeafbeefdeadbeefdeafbeefdeadbeefdeafbeefdeadbeef
            *:tag

        Comments are allowed, and should start with '#':
            # some comment
            some/repository:tag  # keep because bla bla
        """

        repos = []
        tags = []
        repo_tags = []
        digests = []
        repo_digests = []

        for raw_line in lines:
            # Remove comment
            try:
                line, comment = raw_line.split('#', 1)
            except ValueError:
                line = raw_line

            line = line.strip()

            if line:
                parts = list(map(lambda s: s.strip(), line.split(':', 1)))

                if len(parts) != 2:
                    raise ValueError(f'Invalid whitelist line: {raw_line}')

                repo, digest_or_tag = parts

                if not repo:
                    raise ValueError(f'Missing repository in whitelist line: {raw_line}')

                if not digest_or_tag:
                    raise ValueError(f'Missing tag or digest in whitelist line: {raw_line}')

                if repo == '*' and digest_or_tag == '*':
                    raise ValueError(f'Invalid whitelist line: {raw_line}')

                is_digest = ':' in digest_or_tag

                if is_digest and not DIGEST_REGEX.match(digest_or_tag):
                    raise ValueError(f'Invalid digest in whitelist line: {raw_line}')

                elif repo == '*':
                    if is_digest:
                        digests.append(digest_or_tag)
                    else:
                        tags.append(digest_or_tag)
                elif digest_or_tag == '*':
                    repos.append(repo)
                else:
                    if is_digest:
                        repo_digests.append((repo, digest_or_tag))
                    else:
                        repo_tags.append((repo, digest_or_tag))

        return repos, tags, repo_tags, digests, repo_digests

    def should_keep(self, item, purger):
        if item.repo in self.repos:
            return True, 'whitelisted by repository wildcard'
        elif item.digest in self.digests:
            return True, f'whitelisted by digest: {digest}'
        elif item.tag in self.tags:
            return True, 'whitelisted by tag wildcard'
        else:
            for repo, tag in self.repo_tags:
                if item.repo == repo and item.tag == tag:
                    return True, 'whitelisted by tag'
            for repo, digest in self.repo_digests:
                if item.repo == repo:
                    if not item.digest:
                        item.digest = purger.registry.get_digest(item.repo, item.tag)
                    if not item.digest:
                        return True, 'digest not found'  # probably already deleted
                    if item.digest == digest:
                        return True, f'whitelisted by digest: {digest}'

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
