import logging
import re

import click
import daiquiri

from .purger import Purger
from .registry import Registry
from . import strategies


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
    help='Repository regex to search', show_default=True,
)
@click.option(
    '--min-keep', default=7, type=click.INT,
    help='Minimal tags to keep', show_default=True,
)
@click.option(
    '--protect-latest/--no-protect-latest', default=True,
    help='Protect \'latest\' tag from deletion', show_default=True,
)
@click.option(
    '--protect-production/--no-protect-production', default=True,
    help='Protect production tags from deletion', show_default=True,
)
@click.option(
    '--max-age', default=6 * 30, type=click.INT,
    help='Maximum age (in days) of tag', show_default=True,
)
@click.option(
    '--max-dev-age', default=3 * 30, type=click.INT,
    help='Maximum age (in days) of dev tag', show_default=True,
)
@click.option(
    '--max-rc-age', default=3 * 30, type=click.INT,
    help='Maximum age (in days) of rc tag', show_default=True,
)
@click.option('--dry-run/--no-dry-run', default=True, help='Dry run')
@click.option('-v', '--verbose', count=True, help='Be verbose')
@click.option('-q', '--quiet', count=True, help='Be quiet')
def main(
    registry_url, username, password,
    repository, repository_regex,
    min_keep, protect_latest, protect_production,
    max_age, max_dev_age, max_rc_age,
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

    purger = Purger(registry=registry, dry_run=dry_run)

    purger.add_strategy(strategies.WhitelistStrategy(keep_latest=True))
    purger.add_strategy(strategies.TimestampTagStrategy(max_age=90))
    purger.add_strategy(strategies.SemverStrategy(max_age_prerelease=90))

    purger.run(repositories)


main()
