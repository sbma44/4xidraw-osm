FROM sbma44/4xidraw-osm:base
ARG DOWNLOAD
ARG S3
EXPOSE 5432

RUN mkdir -p ./script
ADD script/load.sh ./script/
ADD script/excerpt.sh ./script/

RUN script/load.sh "$DOWNLOAD"

ENTRYPOINT [ "./script/excerpt.sh" ]