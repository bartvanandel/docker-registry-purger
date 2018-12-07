import logging
import re

import click
import daiquiri

from .purger import Purger
from .registry import Registry
from . import strategies, __version__


logger = daiquiri.getLogger(__name__)


def setup_logging(verbosity):
    levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
    verbosity = min(max(0, verbosity), len(levels) - 1)
    daiquiri.setup(level=levels[verbosity])


@click.command()  # noqa: C901 # Skip warning: 'main' is too complex
@click.argument('registry-url')
@click.option(
    '-u', '--username', default=None, type=click.STRING,
    help='Username', show_default=False,
)
@click.option(
    '-p', '--password', default=None, type=click.STRING,
    help='Password', show_default=False,
)
@click.option(
    '--repository', default=None, type=click.STRING, multiple=True,
    help='Repository (i.e., Docker image name) to search', show_default=True,
)
@click.option(
    '--repository-regex', default=None, type=click.STRING,
    help='Repository regex to search'
)
@click.option(
    '--whitelist-file', default=None, type=click.STRING,
    help='Whitelist file'
)
@click.option(
    '--keep-latest-tag/--no-keep-latest-tag', default=True,
    help='Protect "latest" tag from deletion', show_default=True,
)
@click.option(
    '--require-semver/--no-require-semver', default=False,
    help='Require all tags (except "latest") to follow the semver release scheme. '
    'When set to True, all non-semver tags will be removed.', show_default=True,
)
@click.option(
    '--max-age-prerelease', default=90, type=click.INT,
    help='Maximum age (in days) of a semver prerelease tag', show_default=True,
)
@click.option(
    '--trust-timestamp-tags/--no-trust-timestamp-tags', default=True,
    help='Trust timestamps in tags', show_default=True,
)
@click.option(
    '-y', '--assume-yes', 'proceed', flag_value=True, default=None,
    help='Assume yes to all questions'
)
@click.option(
    '-n', '--assume-no', 'proceed', flag_value=False, default=None,
    help='Assume no to all questions'
)
@click.option('--dry-run/--no-dry-run', default=False, help='Dry run')
@click.option('-v', '--verbose', count=True, help='Be verbose')
@click.option('-q', '--quiet', count=True, help='Be quiet')
@click.version_option(__version__, prog_name='docker-registry-purger')
def main(
    registry_url, username, password,
    repository, repository_regex,
    whitelist_file,
    keep_latest_tag,
    require_semver,
    max_age_prerelease,
    trust_timestamp_tags,
    proceed,
    dry_run,
    verbose, quiet,
):
    setup_logging(1 + quiet - verbose)

    registry = Registry(registry_url, username, password)

    if repository:
        repositories = repository
    else:
        repositories = registry.list_repositories()

    if repository_regex:
        repository_regex = re.compile(repository_regex)
        repositories = list(filter(repository_regex.search, repositories))
        logger.info('Only checking these repositories: %s', ', '.join(repositories))

    purger = Purger(registry=registry, dry_run=dry_run, proceed=proceed)

    purger.add_strategy(strategies.WhitelistStrategy(
        keep_latest=keep_latest_tag,
        filename=whitelist_file,
    ))
    purger.add_strategy(strategies.SemverStrategy(
        max_age_prerelease=max_age_prerelease,
        trust_timestamp_tags=trust_timestamp_tags,
        require_semver=require_semver,
    ))
    if trust_timestamp_tags:
        purger.add_strategy(strategies.TimestampTagStrategy(
            max_age=max_age_prerelease
        ))

    purger.run(repositories)


if __name__ == "__main__":
    main()
