import daiquiri
import datetime
import isodate
import json
import requests
import urllib.parse as urlparse


logger = daiquiri.getLogger(__name__)


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
        repositories = self._get('_catalog').json()['repositories']
        logger.debug('Found repositories: %s', ', '.join(repositories))
        return repositories

    def list_tags(self, repository):
        tags = self._get(f'{repository}/tags/list').json()['tags'] or []
        logger.debug('Found tags: %s', ', '.join(tags))
        return tags

    def delete_digest(self, repository, digest):
        return self._delete(f'{repository}/manifests/{digest}')

    def get_manifest(self, repository, tag, with_history=True):
        # Retrieving a 'fat manifest' (i.e. manifest with history) is currently *very* slow in Nexus
        # (many seconds per request), see https://issues.sonatype.org/browse/NEXUS-15277
        # Therefore we provide an option to skip downloading history

        response = self._get(f'{repository}/manifests/{tag}', headers={
            'Accept':
                'application/vnd.docker.distribution.manifest.list.v2+json' if with_history
                else 'application/vnd.docker.distribution.manifest.v2+json'
        })
        return response.json(), response.headers.get('Docker-Content-Digest', False)

    def get_digest(self, repository, tag):
        _, digest = self.get_manifest(repository, tag, False)
        return digest

    def get_age(self, repository, tag):
        info, digest = self.get_manifest(repository, tag, True)
        history = info.get('history')
        if history:
            last_update = max([
                isodate.parse_date(json.loads(line['v1Compatibility']).get('created'))
                for line in history
            ])
            return (datetime.date.today() - last_update).days, digest
        else:
            return None, digest

    def delete_tag(self, repository, tag):
        _, digest = self.get_digest(repository, tag)
        if digest:
            return self.delete_digest(repository, digest)
        else:
            logger.warn('Already deleted: %s:%s', repository, tag)

    def delete_digest_or_tag(self, repository, digest, tag):
        if digest:
            return self.delete_digest(repository, digest)
        elif tag:
            return self.delete_tag(repository, tag)
        else:
            logger.error('Neither digest nor tag were provided, skipping delete')
