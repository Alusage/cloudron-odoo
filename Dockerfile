FROM cloudron/base:5.0.0
# cloudron/base:5.0.0 = Ubuntu 24.04 (Noble), Python 3.12, nginx et gosu inclus.
# Reference: https://github.com/odoo/docker/blob/master/18.0/Dockerfile

ENV LANG=C.UTF-8
ENV ODOO_VERSION=18.0
ENV ODOO_SOURCE=OCA/OCB
ENV DEPTH_DEFAULT=100
ENV DEPTH_MERGE=500
# Noble applique PEP 668 : pip refuse d'ecrire dans le site-packages systeme
# sans cette variable.
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN mkdir -p /app/code /app/pkg /app/data /app/code/auto/addons
WORKDIR /app/code

# Dependances systeme. Noble fournit postgresql-client-16 nativement : pas
# besoin du depot pgdg ni d'apt-key (deprecie).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl wget git gnupg gettext-base xz-utils \
    fonts-noto-cjk node-less npm \
    postgresql-client-16 \
    python3-dev python3-pip python3-setuptools python3-wheel \
    libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libpq-dev \
    libtiff-dev libjpeg8-dev libopenjp2-7-dev zlib1g-dev libfreetype-dev \
    liblcms2-dev libwebp-dev libharfbuzz-dev libfribidi-dev libxcb1-dev \
    libev-dev libssl-dev libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# wkhtmltopdf. Le paquet Noble (0.12.6-2build2) est compile sans le Qt patche,
# ce qui casse les en-tetes/pieds de page des rapports Odoo. On installe donc
# le .deb jammy officiel, qui s'installe et fonctionne sur Noble.
RUN curl -o wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb && \
    echo "967390a759707337b46d1c02452e2bb6b2dc6d59 wkhtmltox.deb" | sha1sum -c - && \
    apt-get update && \
    apt-get install -y --no-install-recommends ./wkhtmltox.deb && \
    rm -rf /var/lib/apt/lists/* wkhtmltox.deb

RUN npm install -g rtlcss

# Cloudron monte un filesystem en lecture seule hors /app/data et /run
RUN rm -rf /var/log/nginx && mkdir -p /run/nginx && ln -s /run/nginx /var/log/nginx

COPY bin/ /usr/local/bin/
COPY patches/ /app/code/patches/

# doodbalib va dans le site-packages de la version de Python de l'image,
# detectee a la volee plutot que codee en dur.
COPY lib/doodbalib /tmp/doodbalib/
RUN PYSITE=$(python3 -c "import site; print(site.getsitepackages()[0])") && \
    cp -r /tmp/doodbalib "${PYSITE}/doodbalib" && \
    rm -rf /tmp/doodbalib && \
    chmod -R a+rX "${PYSITE}/doodbalib"

COPY custom /app/code/custom
RUN chmod -R a+rx /usr/local/bin && sync

RUN git config --global user.email "cloudron@localhost" && \
    git config --global user.name "Cloudron service"

# Odoo depuis OCA/OCB : source unique de l'image, coherente avec ODOO_SOURCE
# et avec les depots OCA agreges dans custom/src.
RUN git clone https://github.com/OCA/OCB.git --depth 1 -b $ODOO_VERSION /app/code/odoo
# --ignore-installed est indispensable partout : l'image de base embarque des
# paquets Python installes par dpkg (cryptography, cffi, setuptools...) sans
# fichier RECORD, que pip refuse de desinstaller pour les mettre a jour.
# setuptools<81 : Odoo importe encore pkg_resources, retire au-dela.
RUN pip3 install --no-cache-dir --ignore-installed "setuptools<81"
RUN pip3 install --no-cache-dir --ignore-installed -e /app/code/odoo && \
    pip3 install --no-cache-dir --ignore-installed -r /app/code/odoo/requirements.txt && \
    pip3 install --no-cache-dir --ignore-installed psycopg2-binary gevent psycogreen git-aggregator

# Patches Cloudron (LDAP displayname, mono-base sql_db et registry).
RUN apply-odoo-patches $ODOO_VERSION

# Agregation des depots OCA/Akretion puis liaison des addons
WORKDIR /app/code/custom/src
RUN gitaggregate -c /app/code/custom/src/repos.yaml --expand-env
RUN /app/code/custom/build.d/110-addons-link
RUN /app/code/custom/build.d/120-dependencies-apt
RUN /app/code/custom/build.d/200-dependencies
RUN /app/code/custom/build.d/400-clean
RUN /app/code/custom/build.d/900-dependencies-cleanup
WORKDIR /app/code

# Jarvis : CLI de maintenance (backup, restore, shell, update de modules),
# identique a celui embarque dans les images odoo_jarvis_assistant. Les chemins
# du layout doodba lui sont passes par variables d'environnement.
ENV JARVIS_ODOO_DIR=/app/code/odoo \
    JARVIS_ADDONS_DIR=/app/code/auto/addons \
    JARVIS_FILESTORE_DIR=/app/data/odoo/filestore \
    JARVIS_ODOO_CONF=/app/data/odoo.conf \
    PATH="/usr/local/bin/jarvis:$PATH"
RUN pip3 install --no-cache-dir --ignore-installed -r /usr/local/bin/jarvis/requirements.txt && \
    chmod +x /usr/local/bin/jarvis/jarvis

# Reconciliation de la pile OpenSSL, obligatoirement en dernier. Une dependance
# transitive (zeep, paramiko, xmlsec, pyjwt, deps de jarvis...) peut faire
# remonter un `cryptography` recent qui a retire le binding `_lib.GEN_EMAIL`
# reference par un vieux pyOpenSSL systeme : Odoo plante alors sur
# `import OpenSSL` avant meme de charger le module base.
RUN pip3 install --no-cache-dir --ignore-installed --upgrade "pyOpenSSL>=24.3.0" cryptography "urllib3<2.0"

ADD start.sh odoo.conf.sample nginx.conf /app/pkg/

RUN mkdir -p /app/data/odoo/filestore /app/data/odoo/addons && \
    chown -R cloudron:cloudron /app/data

CMD [ "/app/pkg/start.sh" ]
