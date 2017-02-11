#!/bin/bash
set -eu
docker run -p0.0.0.0:5433:5432 -t -i $1 bash
