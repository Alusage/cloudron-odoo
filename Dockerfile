FROM cloudron/base:3.2.0@sha256:ba1d566164a67c266782545ea9809dc611c4152e27686fd14060332dd88263ea
# Reference: https://github.com/odoo/docker/blob/master/16.0/Dockerfile

RUN mkdir -p /app/code /app/pkg /app/data /app/code/auto/addons
WORKDIR /app/code

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    dirmngr \
    fonts-noto-cjk \
    gnupg \
    libssl-dev \
    node-less \
    npm \
    python3-num2words \
    python3-pdfminer \
    python3-pip \
    python3-phonenumbers \
    python3-pyldap \
    python3-qrcode \
    python3-renderpm \
    python3-setuptools \
    python3-slugify \
    python3-vobject \
    python3-watchdog \
    python3-xlrd \
    python3-xlwt \
    xz-utils \
    python3-cffi

RUN curl -o wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.5/wkhtmltox_0.12.5-1.focal_amd64.deb \
    && apt-get install -y --no-install-recommends ./wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* wkhtmltox.deb

RUN npm install -g rtlcss

COPY bin/* /usr/local/bin/

COPY lib/doodbalib /usr/local/lib/python3.8/dist-packages/doodbalib
COPY custom /app/code/custom
RUN chmod -R a+rx /usr/local/bin \
    && chmod -R a+rX /usr/local/lib/python3.8/dist-packages/doodbalib \
    && sync

# Install Odoo
# sync extra addons

ENV ODOO_VERSION=16.0
ENV ODOO_SOURCE=OCA/OCB
ENV DEPTH_DEFAULT=100
ENV DEPTH_MERGE=500
RUN git config --global user.email "$CLOUDRON_MAIL_SMTP_USERNAME"
RUN git config --global user.name "Cloudron service"

RUN /app/code/custom/build.d/200-dependencies

# RUN curl -L https://github.com/odoo/odoo/archive/${ODOO_COMMIT_HASH}.tar.gz | tar zx --strip-components 1 -C /app/code && \
RUN git clone https://github.com/odoo/odoo.git --depth 1 -b $ODOO_VERSION /app/code/odoo
WORKDIR /app/code/odoo
RUN git pull -r
WORKDIR /app/code
RUN pip3 install -e /app/code/odoo
RUN pip3 install cffi==1.15.0
RUN pip3 install wheel && \
    pip3 install -r https://raw.githubusercontent.com/$ODOO_SOURCE/$ODOO_VERSION/requirements.txt && \
    pip3 install psycopg2==2.8.6 \
    && pip3 install git-aggregator \
    && (python3 -m compileall -q /usr/local/lib/python3.8/ || true)

# Patch Odoo to prevent connecting to the default database named 'postgres' every now and then.
RUN  sed -i.bak "791i\    to = tools.config['db_name']" /app/code/odoo/odoo/sql_db.py

# Properly map the LDAP attribute 'displayname' instead of 'cn' to the display name of the logged in user.
RUN  sed -i.bak "198s/'cn'/'displayname'/" /app/code/odoo/addons/auth_ldap/models/res_company_ldap.py

RUN rm -rf /var/log/nginx && mkdir /run/nginx && ln -s /run/nginx /var/log/nginx

WORKDIR /app/code/custom/src
RUN gitaggregate -c /app/code/custom/src/repos.yaml --expand-env
RUN /app/code/custom/build.d/110-addons-link
RUN /app/code/custom/build.d/200-dependencies
RUN /app/code/custom/build.d/400-clean
RUN /app/code/custom/build.d/900-dependencies-cleanup

# Copy entrypoint script and Odoo configuration file
ADD start.sh odoo.conf.sample nginx.conf /app/pkg/

RUN mkdir -p /app/data/odoo/filestore /app/data/odoo/addons && \
    chown -R cloudron:cloudron /app/data

CMD [ "/app/pkg/start.sh" ]
