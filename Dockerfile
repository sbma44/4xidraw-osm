FROM sbma44/4xidraw-osm-base:1
ARG DOWNLOAD
EXPOSE 5432

RUN mkdir -p ./script
ADD script/load.sh ./script/
ADD script/excerpt.sh ./script/
RUN mkdir -p /root/.aws
ADD aws-config /root/.aws/config
RUN chmod a+x script/*

RUN script/load.sh "$DOWNLOAD"

ENTRYPOINT [ "./script/excerpt.sh" ]