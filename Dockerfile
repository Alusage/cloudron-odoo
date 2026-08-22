FROM cloudron/base:5.0.0
# FROM cloudron/base:3.2.0@sha256:ba1d566164a67c266782545ea9809dc611c4152e27686fd14060332dd88263ea
# Reference: https://github.com/odoo/docker/blob/master/15.0/Dockerfile

RUN mkdir -p /app/code /app/pkg /app/data /app/code/auto/addons
WORKDIR /app/code

# Add postgresql repository

RUN sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/postgresql.list'
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
RUN cat /etc/apt/sources.list.d/postgresql.list

RUN apt-key del 656408E390CFB1F5
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 656408E390CFB1F5
RUN apt update
#RUN pip install --upgrade pip setuptools

RUN apt-get update && \
    apt-get install -y \
    python3-dev libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev \
    libtiff5-dev libjpeg8-dev libopenjp2-7-dev zlib1g-dev libfreetype6-dev \
    liblcms2-dev libwebp-dev libharfbuzz-dev libfribidi-dev libxcb1-dev libpq-dev python3-wheel libev-dev libssl-dev libffi-dev

RUN curl -o wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb && \
    apt-get install -y --no-install-recommends ./wkhtmltox.deb && \
    rm -f ./wkhtmltox.deb && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt

RUN apt search postgresql-client
RUN apt install postgresql-client-16
RUN npm install -g rtlcss

COPY bin/* /usr/local/bin/
COPY requirements.txt /app/code/

COPY lib/doodbalib /usr/local/lib/python3.12/dist-packages/doodbalib
COPY custom /app/code/custom
RUN chmod -R a+rx /usr/local/bin \
    && chmod -R a+rX /usr/local/lib/python3.12/dist-packages/doodbalib \
    && sync

# Install Odoo
# sync extra addons

ENV ODOO_VERSION=18.0
ENV ODOO_SOURCE=OCA/OCB
ENV DEPTH_DEFAULT=100
ENV DEPTH_MERGE=500
RUN git config --global user.email "$CLOUDRON_MAIL_SMTP_USERNAME"
RUN git config --global user.name "Cloudron service"

# RUN curl -L https://github.com/odoo/odoo/archive/${ODOO_COMMIT_HASH}.tar.gz | tar zx --strip-components 1 -C /app/code && \
RUN git clone https://github.com/odoo/odoo.git --depth 1 -b $ODOO_VERSION /app/code/odoo
WORKDIR /app/code/odoo
RUN git pull -r
WORKDIR /app/code
RUN pip3 install --break-system-packages -e /app/code/odoo
RUN pip3 install --break-system-packages --no-binary :all: gevent && \
    pip3 install --break-system-packages -r /app/code/requirements.txt && \
    pip3 install --break-system-packages psycopg2==2.9.9 \
    && pip3 install --break-system-packages "pyOpenSSL>=23.1.0" \
    && pip3 install --break-system-packages git-aggregator \
    && (python3 -m compileall -q /usr/local/lib/python3.12/ || true)

# Patch Odoo to prevent connecting to the default database named 'postgres' every now and then.
RUN  sed -i.bak "803i\    to = tools.config['db_name']" /app/code/odoo/odoo/sql_db.py

# Properly map the LDAP attribute 'displayname' instead of 'cn' to the display name of the logged in user.
RUN  sed -i.bak "214s/'cn'/'displayname'/" /app/code/odoo/addons/auth_ldap/models/res_company_ldap.py

RUN rm -rf /var/log/nginx && mkdir /run/nginx && ln -s /run/nginx /var/log/nginx

# Copy entrypoint script and Odoo configuration file
ADD start.sh odoo.conf.sample nginx.conf /app/pkg/


WORKDIR /app/code/custom/src
RUN gitaggregate -c /app/code/custom/src/repos.yaml --expand-env
RUN /app/code/custom/build.d/110-addons-link
RUN /app/code/custom/build.d/200-dependencies
RUN /app/code/custom/build.d/400-clean
RUN /app/code/custom/build.d/900-dependencies-cleanup

RUN pip3 install --break-system-packages "pyOpenSSL>=23.1.0"
RUN mkdir -p /app/data/odoo/filestore /app/data/odoo/addons && \
    chown -R cloudron:cloudron /app/data

CMD [ "/app/pkg/start.sh" ]
