#!/bin/bash

# X: 270mm
# Y: 200mm

set -eu -o pipefail

DBNAME="osm"
CLIP="$1"
BUCKET="$2"
PSQL="psql -U postgres -t -q $DBNAME"
TMP="/tmp/4xidraw/out"
mkdir -p "$TMP"

# debug mode for docker
if [ -n "${DEBUG:-}" ]; then
  while [ 1 ]; do
    sleep 60
  done
fi

rm $TMP/* || true

service postgresql start

KARTOGRAPH_JSON="{
      \"proj\": { \"id\": \"lonlat\" },
      \"layers\": {
"

i=0
CRITERIA="highway|planet_osm_line|highway IS NOT NULL
bicycle|planet_osm_line|route='bicycle'
train|planet_osm_line|route='train'
building|planet_osm_polygon|building IS NOT NULL"
echo "$CRITERIA" > $TMP/criteria
while IFS='' read -r criterion; do
  LABEL="$(echo $criterion | cut -d '|' -f 1)"
  TABLE="$(echo $criterion | cut -d '|' -f 2)"
  WHERE="$(echo $criterion | cut -d '|' -f 3)"
  echo "DROP TABLE IF EXISTS excerpt_$LABEL;" | $PSQL
  echo "CREATE TABLE excerpt_$LABEL AS SELECT * FROM \"$TABLE\"
    WHERE
      ST_Intersects(way, ST_SetSRID(ST_GeomFromGeoJSON('$CLIP'), 4326))
    AND
      $WHERE;" | $PSQL
  echo "ALTER TABLE excerpt ALTER COLUMN way SET DATA TYPE geometry;" | $PSQL
  echo "UPDATE excerpt_$LABEL SET way=ST_SetSRID(ST_Intersection(way, ST_SetSRID(ST_GeomFromGeoJSON('$CLIP'), 4326)), 4326);" | $PSQL

  if [ "$(echo "SELECT COUNT(*) FROM excerpt_$LABEL;" | $PSQL)" -gt 0 ]; then
    if [ "$i" -gt 0 ]; then KARTOGRAPH_JSON="$KARTOGRAPH_JSON,"; fi
    KARTOGRAPH_JSON="$KARTOGRAPH_JSON
        \"$LABEL\": {
          \"src\": \"postgis:dbname=$DBNAME user=postgres\",
          \"table\": \"excerpt_$LABEL\"
        }"
    i=$((i+1))
  fi
done < $TMP/criteria

KARTOGRAPH_JSON="$KARTOGRAPH_JSON
      }
    }"
echo "$KARTOGRAPH_JSON" > $TMP/../config.json
SNAPSHOT="${DBNAME}-$(date '+%s')"
kartograph $TMP/../config.json -o $TMP/$SNAPSHOT.svg

# convert groups to inkscape layers
sed 's/<g /<g inkscape:groupmode="layer" /g' < $TMP/$SNAPSHOT.svg > $TMP/$SNAPSHOT.svg.new && mv $TMP/$SNAPSHOT.svg.new $TMP/$SNAPSHOT.svg

# compress & upload
(cd $TMP && zip "$TMP/$SNAPSHOT.zip" $SNAPSHOT.svg)
aws s3 cp "$TMP/$SNAPSHOT.zip" "$BUCKET/$SNAPSHOT.zip"

echo "done!"
echo "s3://sbma44-4xidraw/$SNAPSHOT.zip"