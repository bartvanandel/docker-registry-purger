# Docker Registry Purger

A simple cleaner for private docker-registries.


## Installation

For a system-wide install:

```sh
pip install docker-registry-purger
```

Alternatively, in a local virtual environment:

```sh
pipenv shell
pip install docker-registry-purger
```


## Usage

Clean registry using standard options (i.e., keep all regular semver releases, remove semver prereleases and timestamped releases older than 90 days).

```sh
docker-registry-purger 'https://[your_repository]' -u username -p password
```

For help on command-line arguments, run:

```
docker-registry-purger --help
```

This script only drops references to blobs, the blobs themself are not deleted,
to remove them you have to follow the procedure describe on
https://docs.docker.com/registry/garbage-collection/#run-garbage-collection.


## Development

To run directly from source, in a local virtual environment:

```sh
cd /path/to/repository
pipenv shell
pip install -r requirements-dev.txt
python -m docker_registry_purger [...args]
```
