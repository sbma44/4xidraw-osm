#!/bin/bash

# X: 270mm
# Y: 200mm

set -eu -o pipefail

DBNAME="$1"
CLIP="$2"
PSQL="psql -U postgres -t -q $DBNAME"
TMP="/tmp/4xidraw/out"
mkdir -p "$TMP"

rm $TMP/* || true

service postgresql start

CRITERIA="highway|planet_osm_line|highway IS NOT NULL
bicycle|planet_osm_line|route='bicycle'
train|planet_osm_line|route='train'
building|planet_osm_polygon|building IS NOT NULL"

echo "$CRITERIA" | while read criterion; do
  LABEL="$(echo $criterion | cut -d '|' -f 1)"
  TABLE="$(echo $criterion | cut -d '|' -f 2)"
  WHERE="$(echo $criterion | cut -d '|' -f 3)"
  echo "DROP TABLE IF EXISTS excerpt;" | $PSQL
  echo "CREATE TABLE excerpt AS SELECT * FROM \"$TABLE\"
    WHERE
      ST_Intersects(way, ST_SetSRID(ST_GeomFromGeoJSON('$CLIP'), 4326))
    AND
      $WHERE;" | $PSQL
  echo "ALTER TABLE excerpt ALTER COLUMN way SET DATA TYPE geometry;" | $PSQL
  echo "UPDATE excerpt SET way=ST_SetSRID(ST_Intersection(way, ST_SetSRID(ST_GeomFromGeoJSON('$CLIP'), 4326)), 4326);" | $PSQL

  if [ "$(echo "SELECT COUNT(*) FROM excerpt;" | $PSQL)" -gt 0 ]; then
    echo "{
      \"proj\": { \"id\": \"lonlat\" },
      \"layers\": {
        \"roads\": {
          \"src\": \"postgis:dbname=$DBNAME user=postgres\",
          \"table\": \"excerpt\"
        }
      }
    }" > $TMP/../$LABEL.json
    kartograph $TMP/../$LABEL.json -o $TMP/$LABEL.svg
  fi
done

OUTFILE="$TMP/${DBNAME}-$(date '+%s').zip"
zip "$OUTFILE" $TMP/*.svg
aws s3 cp "$OUTFILE" s3://sbma44-4xidraw/$(basename $OUTFILE)
rm "$OUTFILE"
rm "$TMP/*.svg"

echo "s3://sbma44-4xidraw/$(basename $OUTFILE)"