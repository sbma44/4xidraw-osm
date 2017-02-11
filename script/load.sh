#!/bin/bash

set -eu -o pipefail

TMP='/tmp/4xidraw'
mkdir -p "$TMP"

service postgresql start

DOWNLOAD="$(echo "$1" | tr ',' ' ')"
for D in $DOWNLOAD; do
    echo "- downloading $D"
    if [ ! -f "$TMP/$(basename $D .bz2)" ]; then
        curl "$D" > "$TMP/$(basename $D)"
        bunzip2 "$TMP/$(basename $D)"
    fi

    DBNAME="$(basename $D .osm.bz2 | tr '-' '_')"
    echo "- creating database $DBNAME"
    dropdb --if-exists -U postgres "$DBNAME"
    createdb -U postgres "$DBNAME"
    echo "CREATE EXTENSION postgis;" | psql -U postgres "$DBNAME"

    echo "- loading into DB $DBNAME"
    osm2pgsql -s -U postgres -d "$DBNAME" "$TMP/$(basename $D .bz2)"

    # this seems dumb but the command line flags don't seem to work
    for g in line point polygon; do
        echo "
            SELECT UpdateGeometrySRID('planet_osm_$g', 'way', 4326);
            UPDATE planet_osm_$g SET way = ST_TRANSFORM( ST_SETSRID( way, 900913), 4326 );" | psql -U postgres $DBNAME
    done

    rm "$TMP/$(basename $D .bz2)"
done

service postgresql stop