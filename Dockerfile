FROM cloudron/base:5.1.0
# Reference: https://github.com/odoo/docker/blob/master/18.0/Dockerfile

RUN mkdir -p /app/code /app/pkg /app/data /app/code/auto/addons
WORKDIR /app/code

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl dirmngr fonts-noto-cjk gnupg libssl-dev node-less npm \
    python3-dev python3-pip python3-setuptools python3-wheel python3-cffi python3-ldap \
    python3-qrcode python3-vobject python3-watchdog python3-xlrd python3-xlwt \
    python3-num2words python3-phonenumbers python3-slugify \
    libxml2-dev libxslt1-dev libsasl2-dev libpq-dev libtiff-dev libjpeg-dev \
    libopenjp2-7-dev zlib1g-dev libfreetype-dev liblcms2-dev libwebp-dev \
    libharfbuzz-dev libfribidi-dev libxcb1-dev xz-utils && \
    rm -rf /var/lib/apt/lists/*

# wkhtmltopdf — version système si Noble, sinon 0.12.6.1 depuis GitHub
RUN CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME") && \
    if [ "$CODENAME" = "noble" ]; then \
        apt-get update && apt-get install -y --no-install-recommends wkhtmltopdf && rm -rf /var/lib/apt/lists/*; \
    else \
        curl -o wkhtmltox.deb -sSL "https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.${CODENAME}_amd64.deb" && \
        apt-get update && apt-get install -y --no-install-recommends ./wkhtmltox.deb && \
        rm -rf /var/lib/apt/lists/* wkhtmltox.deb; \
    fi

RUN npm install -g rtlcss

COPY bin/* /usr/local/bin/

# Installer doodbalib dans le bon site-packages selon la version Python de l'image
COPY lib/doodbalib /tmp/doodbalib/
RUN PYSITE=$(python3 -c "import site; print(site.getsitepackages()[0])") && \
    cp -r /tmp/doodbalib "${PYSITE}/doodbalib" && \
    rm -rf /tmp/doodbalib && \
    chmod -R a+rX "${PYSITE}/doodbalib"

COPY custom /app/code/custom
RUN chmod -R a+rx /usr/local/bin && sync

ENV ODOO_VERSION=18.0
ENV ODOO_SOURCE=OCA/OCB
ENV DEPTH_DEFAULT=100
ENV DEPTH_MERGE=500
RUN git config --global user.email "cloudron@localhost" && \
    git config --global user.name "Cloudron service"

# Ubuntu Noble (24.04) bloque pip system-wide par défaut (PEP 668)
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Odoo 18 depuis OCA/OCB
RUN git clone https://github.com/OCA/OCB.git --depth 1 -b $ODOO_VERSION /app/code/odoo
RUN pip3 install --no-cache-dir -e /app/code/odoo && \
    pip3 install --no-cache-dir -r /app/code/odoo/requirements.txt && \
    pip3 install --no-cache-dir psycopg2-binary git-aggregator

# Agréger les dépôts OCA/Akretion, puis lier les addons
WORKDIR /app/code/custom/src
RUN gitaggregate -c /app/code/custom/src/repos.yaml --expand-env
RUN /app/code/custom/build.d/110-addons-link
RUN /app/code/custom/build.d/200-dependencies
RUN /app/code/custom/build.d/400-clean
RUN /app/code/custom/build.d/900-dependencies-cleanup

RUN mkdir -p /app/data/odoo/filestore /app/data/odoo/addons && \
    chown -R cloudron:cloudron /app/data

CMD [ "/app/pkg/start.sh" ]
