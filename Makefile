.PHONY: test test-integration test-all build publish clean

test:
	pytest tests/ -v -m "not integration"

test-integration:
	pytest tests/ -v -m integration

test-all:
	pytest tests/ -v

build: clean
	python -m build

publish: build
	twine upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info/
