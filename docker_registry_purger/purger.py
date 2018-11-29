import daiquiri
import datetime
from natsort import natsorted
import re

from .semver import Semver
from .utils import query_yes_no


logger = daiquiri.getLogger(__name__)


class Item:
    def __init__(self, repo, tag=None, digest=None, age=None, keep=None):
        if not tag and not digest:
            raise ValueError('Either tag or digest must have a value')

        self.repo = repo
        self.tag = tag
        self.digest = digest
        self.age = age
        self.keep = keep


class Purger:
    def __init__(self, registry, strategies=[], proceed=None, dry_run=False):
        self.registry = registry
        self.strategies = strategies
        self.proceed = proceed
        self.dry_run = dry_run

    def add_strategy(self, strategy):
        self.strategies.append(strategy)

    def run(self, repos):
        # Phase/pass 1: gather items
        logger.info('Phase 1: gather items ...')
        repo_items = {repo: self.gather_items(repo) for repo in repos}

        # Phase 2: mark items for deletion
        logger.info('Phase 2: mark items for deletion ...')
        for items in repo_items.values():
            self.mark_items(items)

        # Flatten
        items = sum(repo_items.values(), [])

        # Report
        logger.info('Keeping %d items', sum(1 for item in items if item.keep == True))
        logger.info('Deleting %d items', sum(1 for item in items if item.keep == False))
        logger.info('Keeping %d undecided items', sum(1 for item in items if item.keep is None))
        logger.debug('Undecided items: %s', ', '.join((f'{item.repo}:{item.tag or item.digest}' for item in items if item.keep is None)))

        if self.proceed == False:
            logger.info('Skipping deletion because proceed=False')
        elif self.proceed == True or query_yes_no('\nProceed with delete?'):
            # Phase 3: delete marked items
            logger.info('Phase 3: delete marked items ...')
            self.delete_marked_items(items)

    def gather_items(self, repo):
        logger.info('Checking repository <%s>', repo)

        items = [Item(repo=repo, tag=tag) for tag in self.registry.list_tags(repo)]
        items = natsorted(items, key=lambda item: (-1 if item.age is None else item.age, item.tag.lower()))

        return items

    def mark_items(self, items):
        for item in items:
            self.mark_item(item)

    def mark_item(self, item):
        for strategy in self.strategies:
            keep = strategy.should_keep(item, self)

            if keep is not None:
                item.keep = keep

                logger.info('Marking for %s: %s:%s (age: %sd)',
                    'keeping' if keep else 'DELETION',
                    item.repo,
                    item.tag or item.digest,
                    '?' if item.age is None else str(item.age))

                # Stop evaluating next strategies once we've found an answer
                break

    def delete_marked_items(self, items):
        for item in items:
            self.delete_marked_item(item)

    def delete_marked_item(self, item):
        if item.keep == False:
            logger.info('%sDeleting %s:%s ...', '[dry run]' if self.dry_run else '', item.repo, item.digest or item.tag)
            if not self.dry_run:
                self.registry.delete_digest_or_tag(item.repo, item.digest, item.tag)
