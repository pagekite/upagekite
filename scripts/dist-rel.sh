#!/bin/bash
rm dist/*

python3 -m build --sdist --wheel
ls -l dist/

echo '=== PRESS ENTER TO UPLOAD TO PyPI ==='
read
twine upload dist/*
