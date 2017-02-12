FROM ubuntu:14.04
ARG DOWNLOAD
EXPOSE 5432

# Configure SHELL
RUN rm /bin/sh && ln -s /bin/bash /bin/sh
ENV SHELL /bin/bash

RUN apt-get update -y && \
    apt-get install -y curl && \
    bash -c "echo \"deb http://apt.postgresql.org/pub/repos/apt/ precise-pgdg main\" | tee /etc/apt/sources.list.d/pgdg.list" && \
    bash -c "echo \"deb http://apt.postgresql.org/pub/repos/apt trusty-pgdg main\" | tee -a /etc/apt/sources.list.d/postgres.list" && \
    bash -c "curl 'https://www.postgresql.org/media/keys/ACCC4CF8.asc' | apt-key add -" && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv 434AC25D && \
    apt-get install -y software-properties-common apt-transport-https && \
    apt-add-repository 'deb https://s3.amazonaws.com/apendleton-public/ppa/stable/ trusty main' && \
    apt-add-repository 'deb https://s3.amazonaws.com/apendleton-public/ppa/unstable/ trusty main' && \
    apt-get update -y && \
    apt-get install -y libpq-dev libgeos-c1 libgeos++-dev libgeos-dev=3.4.2-4ubuntu1 proj-bin libspatialite5=4.1.1-5ubuntu1 unzip zip && \
    apt-get install -y postgresql-9.6 postgresql-client-9.6 postgresql-contrib-9.6 postgresql-plpython-9.6 postgresql-9.6-postgis-scripts postgresql-common postgresql-client-common postgis=2.3.2+dfsg-1~exp1.pgdg14.04+1
RUN apt-get install -y python-software-properties python-setuptools python-dev build-essential gcc-4.7 gcc g++ git libprotobuf8 libprotobuf-dev protobuf-compiler libprotobuf-dev libsqlite3-dev libdbd-xbase-perl gdal-bin=1.11.2+dfsg-1~exp2~trusty bc pkg-config libpng12-dev sqlite3 jq p7zip p7zip-full ruby parallel psmisc htop wget zip unzip libxslt1-dev python-dev python-pyproj python-psycopg2 python-gdal=1.10.1+dfsg-5ubuntu1 python-pip && \
    apt-get autoremove -y && \
    apt-get autoclean -y
RUN pip install shapely
RUN chmod a+rx $HOME && \
    easy_install pip && \
    pip install --upgrade pip && \
    pip install csvkit awscli
RUN pip install https://github.com/kartograph/kartograph.py/zipball/master -r https://raw.github.com/kartograph/kartograph.py/master/requirements.txt
RUN apt-get install -y --no-install-recommends osm2pgsql tmux vim

# custom postgres settings
RUN bash -c "echo \"max_locks_per_transaction=512\" >> /etc/postgresql/9.6/main/postgresql.conf"
RUN bash -c "echo \"max_connections=1000\" >> /etc/postgresql/9.6/main/postgresql.conf"
ADD ./pg_hba.conf /tmp/pg_hba.conf
RUN cp /tmp/pg_hba.conf /etc/postgresql/9.6/main/pg_hba.conf
RUN echo "listen_addresses = '*'" >> /etc/postgresql/9.6/main/postgresql.conf

RUN mkdir -p ./script
ADD script/load.sh ./script/
ADD script/excerpt.sh ./script/
RUN mkdir -p /root/.aws
ADD aws-config /root/.aws/config
RUN chmod a+x script/*

RUN script/load.sh "$DOWNLOAD"

ENTRYPOINT [ "./script/excerpt.sh" ]