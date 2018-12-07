.PHONY: update docs quality tests clean

update:
	pip install -r requirements-dev.txt
	pip install -e .

quality:
	python setup.py check --strict --metadata
	check-manifest
	flake8

clean:
	find . "(" -name '*.so' -or -name '*.egg' -or -name '*.pyc' -or -name '*.pyo' ")" -delete
	find . -type d -name __pycache__ -exec rm -r {} \;
	rm -rf .tox .cache build dist
