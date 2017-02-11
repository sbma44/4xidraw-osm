#!/bin/bash
docker build --build-arg DOWNLOAD=http://download.geofabrik.de/north-america/us/district-of-columbia-latest.osm.bz2 $(dirname $0)/..
