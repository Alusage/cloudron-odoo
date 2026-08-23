#!/bin/bash
set -euo pipefail

export LANG="C.UTF-8"
export ODOO_RC="/app/data/odoo.conf"

pg_cli() {
  PGPASSWORD=$CLOUDRON_POSTGRESQL_PASSWORD psql \
    -h $CLOUDRON_POSTGRESQL_HOST \
    -p $CLOUDRON_POSTGRESQL_PORT \
    -U $CLOUDRON_POSTGRESQL_USERNAME \
    -d $CLOUDRON_POSTGRESQL_DATABASE -c "$1"
}

# Create required directories if they don't exist
mkdir -p /app/data/extra-addons /app/data/odoo /run/odoo /run/nginx
chown -R cloudron:cloudron /run /app/data

# Check for First Run
if [[ ! -f /app/data/odoo.conf ]]; then

  echo "First run. Initializing DB..."

  # Initialize the database, and exit.
  /usr/local/bin/gosu cloudron:cloudron /app/code/odoo/odoo-bin -i base,auth_ldap,fetchmail --without-demo all --data-dir /app/data/odoo --logfile /run/odoo/runtime.log -d $CLOUDRON_POSTGRESQL_DATABASE --db_host $CLOUDRON_POSTGRESQL_HOST --db_port $CLOUDRON_POSTGRESQL_PORT --db_user $CLOUDRON_POSTGRESQL_USERNAME --db_pass $CLOUDRON_POSTGRESQL_PASSWORD --stop-after-init

  echo "Initialized successfully."

  # echo "Adding required tables/relations for mail settings."
  
  pg_cli "INSERT INTO public.ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date) VALUES ('base_setup.default_external_email_server', 'True', 2, 'NOW()', 2, 'NOW()');"
  pg_cli "INSERT INTO public.ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date) VALUES ('mail.catchall.domain', '$CLOUDRON_APP_DOMAIN', 2, 'NOW()', 2, 'NOW()');"

  echo "Disabling public sign-up..."
  pg_cli "UPDATE public.ir_config_parameter SET value='b2b' WHERE key='auth_signup.invitation_scope';"

  echo "Copying default configuration file to /app/data/odoo.conf..."
  cp /app/pkg/odoo.conf.sample /app/data/odoo.conf
  crudini --set /app/data/odoo.conf 'options' list_db "True"
  admin_password_hashed=$(/usr/bin/python3 /usr/local/bin/hash_password.py "$CLOUDRON_MAIL_SMTP_PASSWORD")
  crudini --set /app/data/odoo.conf 'options' admin_password "$admin_password_hashed"
  echo "First run complete."
fi

# These values should be re-set to make Odoo work as expcected.
echo "Ensuring proper [options] in /app/data/odoo.conf ..."

#/usr/local/bin/gosu cloudron:cloudron /app/code/odoo/odoo-bin -i auth_ldap,fetchmail -d $CLOUDRON_POSTGRESQL_DATABASE -c /app/data/odoo.conf --db_host $CLOUDRON_POSTGRESQL_HOST --db_port $CLOUDRON_POSTGRESQL_PORT --db_user $CLOUDRON_POSTGRESQL_USERNAME --db_pass $CLOUDRON_POSTGRESQL_PASSWORD --without-demo all --stop-after-init

# Check if asking update
if [[ -f /app/data/update ]]; then
  gosu cloudron:cloudron /app/code/odoo/odoo-bin -u all -d $CLOUDRON_POSTGRESQL_DATABASE -r $CLOUDRON_POSTGRESQL_USERNAME -w $CLOUDRON_POSTGRESQL_PASSWORD --db_host $CLOUDRON_POSTGRESQL_HOST --db_port $CLOUDRON_POSTGRESQL_PORT   --without-demo all --stop-after-init --addons-path /app/data/extra-addons,/app/code/auto/addons,/app/code/odoo/addons
fi

# Custom paths
crudini --set /app/data/odoo.conf 'options' addons_path "/app/data/extra-addons,/app/code/auto/addons,/app/code/odoo/addons"
crudini --set /app/data/odoo.conf 'options' data_dir "/app/data/odoo"

# Logging
crudini --set /app/data/odoo.conf 'options' logfile "/run/logs/odoo.log"
crudini --set /app/data/odoo.conf 'options' logrotate 'False'
crudini --set /app/data/odoo.conf 'options' log_db 'False'
crudini --set /app/data/odoo.conf 'options' syslog 'False'

# Http Server
crudini --set /app/data/odoo.conf 'options' proxy_mode "True"
crudini --set /app/data/odoo.conf 'options' secure 'False'
crudini --set /app/data/odoo.conf 'options' interface '127.0.0.1'
crudini --set /app/data/odoo.conf 'options' port '8069'
crudini --set /app/data/odoo.conf 'options' longpolling_port 'False'
crudini --set /app/data/odoo.conf 'options' gevent_port '8072'
crudini --set /app/data/odoo.conf 'options' limit_time_cpu '1200'
crudini --set /app/data/odoo.conf 'options' limit_time_real '1200'
# Securing Odoo
crudini --set /app/data/odoo.conf 'options' test_enable "False"
crudini --set /app/data/odoo.conf 'options' test_file "False"
crudini --set /app/data/odoo.conf 'options' test_report_directory "False"
crudini --set /app/data/odoo.conf 'options' without_demo "all"
crudini --set /app/data/odoo.conf 'options' debug_mode "False"
#TODO Disable debug mode

# DB
crudini --set /app/data/odoo.conf 'options' db_host "$CLOUDRON_POSTGRESQL_HOST"
crudini --set /app/data/odoo.conf 'options' db_port "$CLOUDRON_POSTGRESQL_PORT"
crudini --set /app/data/odoo.conf 'options' db_user "$CLOUDRON_POSTGRESQL_USERNAME"
crudini --set /app/data/odoo.conf 'options' db_password "$CLOUDRON_POSTGRESQL_PASSWORD"
crudini --set /app/data/odoo.conf 'options' db_name "$CLOUDRON_POSTGRESQL_DATABASE"
crudini --set /app/data/odoo.conf 'options' db_filter "^$CLOUDRON_POSTGRESQL_DATABASE.*$"
crudini --set /app/data/odoo.conf 'options' db_sslmode 'False'

# IMAP Configuration
# if [[ -z "${CLOUDRON_MAIL_IMAP_SERVER+x}" ]]; then
#   echo "IMAP is disabled. Removing values from config."
#   pg_cli "UPDATE public.fetchmail_server SET active='f' WHERE name LIKE 'Cloudron%';"
# else
#   echo "IMAP is enabled. Adding values to config."
#   pg_cli "INSERT INTO public.fetchmail_server (id, name, active, state, server, port, server_type, is_ssl, attach, original, date, \"user\", password, object_id, priority, configuration, script, create_uid, create_date, write_uid, write_date) VALUES (1, 'Cloudron IMAP Service', true, 'done', '$CLOUDRON_MAIL_IMAP_SERVER', $CLOUDRON_MAIL_IMAP_PORT, 'imap', false, true, false, NULL, '$CLOUDRON_MAIL_IMAP_USERNAME', '$CLOUDRON_MAIL_IMAP_PASSWORD', 151, 5, NULL, '/mail/static/scripts/odoo-mailgate.py', 2, 'NOW()', 2, 'NOW()') ON CONFLICT (id) DO NOTHING;"
# fi

# SMTP Configuration
# if [[ -z "${CLOUDRON_MAIL_SMTP_SERVER+x}" ]]; then
#   echo "SMTP is disabled. Removing values from config."
#   pg_cli "UPDATE public.ir_mail_server SET active='f' WHERE name LIKE 'Cloudron%';"
# else
#   echo "SMTP is enabled. Adding values to config."
#   pg_cli "INSERT INTO public.ir_mail_server (id, name, smtp_host, smtp_port, smtp_user, smtp_pass, smtp_encryption, smtp_debug, sequence, active, create_uid, create_date, write_uid, write_date) VALUES (1, 'Cloudron SMTP Service', '$CLOUDRON_MAIL_SMTP_SERVER', $CLOUDRON_MAIL_SMTP_PORT, '$CLOUDRON_MAIL_SMTP_USERNAME', '$CLOUDRON_MAIL_SMTP_PASSWORD', 'none', false, 10, true, 2, 'NOW()', 2, 'NOW()') ON CONFLICT (id) DO NOTHING;"
# fi

# LDAP Configuration
if [[ -z "${CLOUDRON_LDAP_SERVER+x}" ]]; then
  echo "LDAP is disabled. Removing values from config."
  pg_cli "DELETE FROM public.res_company_ldap WHERE id = 1 AND company = 1"
else
  echo "LDAP is enabled. Adding values to config."
  pg_cli "INSERT INTO public.res_company_ldap (id, sequence, company, ldap_server, ldap_server_port, ldap_binddn, ldap_password, ldap_filter, ldap_base, \"user\", create_user, ldap_tls, create_uid, create_date, write_uid, write_date) VALUES (1, 10, 1, '$CLOUDRON_LDAP_SERVER', $CLOUDRON_LDAP_PORT, '$CLOUDRON_LDAP_BIND_DN', '$CLOUDRON_LDAP_BIND_PASSWORD', '(&(objectclass=user)(mail=%s))', '$CLOUDRON_LDAP_USERS_BASE_DN', NULL, true, false, 2, 'NOW()', 2, 'NOW()') ON CONFLICT (id) DO NOTHING;;"
fi

# Start nginx process
sed -e "s,__REPLACE_WITH_CLOUDRON_APP_DOMAIN__,${CLOUDRON_APP_DOMAIN}," /app/pkg/nginx.conf >/run/nginx/nginx.conf

if [[ ! -f /app/data/nginx-custom-locations.conf ]]; then
  cat >/app/data/nginx-custom-locations.conf <<EOF
# Content of this file is included inside the server { } block.
# Add custom locations except "/" and "/longpolling" as they are reserved for Odoo.
# Or add custom directives. See https://nginx.org/en/docs/http/ngx_http_core_module.html#server
EOF
fi

echo "=> Start nginx"
rm -f /run/nginx.pid

nginx -c /run/nginx/nginx.conf &
# Done nginx

echo "Resource allocation (hard limit: 100% of available memory; soft limit: 80%)"
if [[ -f /sys/fs/cgroup/memory/memory.memsw.limit_in_bytes ]]; then
  memory_limit_hard=$(($(cat /sys/fs/cgroup/memory/memory.memsw.limit_in_bytes)))
  memory_limit_soft=$((memory_limit_hard / 5 * 4))
else
  memory_limit_hard=2684354560
  memory_limit_soft=2147483648 # (memory_limit_hard * 4 / 5)
fi

worker_count=$((memory_limit_hard / 1024 / 1024 / 150)) # 1 worker for 150M
worker_count=$((worker_count > 8 ? 8 : worker_count))   # max of 8
worker_count=$((worker_count < 1 ? 1 : worker_count))   # min of 1

echo "Memory limits - hard limit: $memory_limit_hard bytes, soft limit: $memory_limit_soft bytes"

crudini --set /app/data/odoo.conf 'options' limit_memory_hard $memory_limit_hard
crudini --set /app/data/odoo.conf 'options' limit_memory_soft $memory_limit_soft
crudini --set /app/data/odoo.conf 'options' workers $worker_count

echo "Done. Starting server with $worker_count workers.."

chown -R cloudron:cloudron /app/data/

/usr/local/bin/gosu cloudron:cloudron /app/code/odoo/odoo-bin -c /app/data/odoo.conf