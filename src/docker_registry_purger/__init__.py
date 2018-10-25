#!/usr/bin/env python
import datetime
import json
import logging
import re
import urllib.parse as urlparse

import click
import daiquiri
import isodate
from natsort import natsorted
import requests

logger = daiquiri.getLogger(__name__)

DEV_REGEX = re.compile(r'(?:\b|\d|_)dev(?:\b|\d|_)', re.IGNORECASE)
RC_REGEX = re.compile(r'(?:\b|\d|_)rc(?:\b|\d|_)', re.IGNORECASE)


class Registry:
    def __init__(self, url, username=None, password=None):
        self.base_url = urlparse.urljoin(url, '/v2/')
        self.username = username
        self.password = password

    def _request(self, method, path, **kwargs):
        kwargs.setdefault('allow_redirects', True)
        return requests.request(
            method=method,
            url=urlparse.urljoin(self.base_url, path),
            auth=(self.username, self.password),

            **kwargs,
        )

    def _get(self, path, **kwargs):
        return self._request('get', path, **kwargs)

    def _delete(self, path, **kwargs):
        return self._request('delete', path, **kwargs)

    def list_repositories(self):
        return self._get('_catalog').json()['repositories']

    def list_tags(self, repository):
        return self._get('{}/tags/list'.format(repository)).json()['tags'] or []

    def delete_digest(self, repository, digest):
        return self._delete('{}/manifests/{}'.format(repository, digest))

    def get_tag(self, repository, tag):
        response = self._get('{}/manifests/{}'.format(repository, tag))
        return response.json(), response.headers.get('Docker-Content-Digest')

    def delete_tag(self, repository, tag):
        _, digest = self.get_tag(repository, tag)
        return self.delete_digest(repository, digest)


def tag_info(registry, repository, tag):
    today = datetime.date.today()
    info, digest = registry.get_tag(repository, tag)

    # Retrieve tag age
    dates = [json.loads(line['v1Compatibility']).get('created') for line in info.get('history', [])]
    last_update = isodate.parse_date(max(dates)) if dates else today
    age = (today - last_update).days

    return tag, digest, age


def setup_logging(verbosity):
    levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
    verbosity = min(max(0, verbosity), len(levels) - 1)
    daiquiri.setup(level=levels[verbosity])


def execute(dry_run, fct, *args, **kwargs):
    """Only execute function on non dry run mode"""
    if not dry_run:
        return fct(*args, **kwargs)


def is_dev(tag):
    return DEV_REGEX.search(tag) is not None

def is_rc(tag):
    return RC_REGEX.search(tag) is not None

def get_release_type(tag):
    if is_dev(tag):
        return 'dev'
    elif is_rc(tag):
        return 'rc'
    else:
        return 'prod'

@click.command()
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
    '--max-age', default=6 * 30, type=click.INT,
    help='Maximum age (in days) of tag', show_default=True,
)
@click.option(
    '--max-dev-age', default=1 * 30, type=click.INT,
    help='Maximum age (in days) of dev tag', show_default=True,
)
@click.option(
    '--max-rc-age', default=3 * 30, type=click.INT,
    help='Maximum age (in days) of rc tag', show_default=True,
)
@click.option('--dry-run/--no-dry-run', default=False, help='Dry run')
@click.option('-v', '--verbose', count=True, help='Be verbose')
@click.option('-q', '--quiet', count=True, help='Be quiet')
def main(registry_url, username, password, repository, repository_regex, min_keep, max_age, max_dev_age, max_rc_age, dry_run, verbose, quiet):
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

    for repository in repositories:
        logger.info('Checking <%s> repository', repository)
        tags = natsorted(
            [tag_info(registry, repository, tag) for tag in registry.list_tags(repository)],
            key=lambda x: (x[2], x[0].lower()),
        )

        count_prod = 0

        for (tag, digest, age) in tags:
            release_type = get_release_type(tag)

            logger.info('Image: %s:%s [%s, age %dd]', repository, tag, release_type, age)

            if not digest:
                logger.warning('Already deleted: %s:%s', repository, tag)
                continue

            if release_type == 'dev':
                if age > max_dev_age:
                    logger.warning('Deleting %s:%s [dev, age %dd]', repository, tag, age)
                    execute(dry_run, registry.delete_digest, repository, digest)

            elif release_type == 'rc':
                if age > max_rc_age:
                    logger.warning('Deleting %s:%s [rc, age %dd]', repository, tag, age)
                    execute(dry_run, registry.delete_digest, repository, digest)

            else:
                count_prod = count_prod + 1

                if count_prod <= min_keep:
                    logger.debug('Keeping %s:%s [prod, %d/%d]', repository, tag, count_prod, min_keep)
                elif age > max_age:
                    logger.warning('Deleting %s:%s [old, age %dd]', repository, tag, age)
                    execute(dry_run, registry.delete_digest, repository, digest)


if __name__ == '__main__':
    daiquiri.setup(level=logging.INFO)
    main()
