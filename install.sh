#!/usr/bin/env bash
# U-Tender native installer (no Docker).
#
# Run as root on a fresh Debian/Ubuntu server, or on any existing one:
#
#     sudo ./install.sh
#
# What it does, in order:
#   1. Installs system packages: Python, Node.js 20, MariaDB (only if no
#      MySQL/MariaDB server is present yet).
#   2. Uses your existing MySQL user 'app_user' (asks for its password;
#      the installer never creates or changes users) to create the
#      database (DB_NAME, default utender_app).
#   3. Writes backend/.env with generated secrets (kept if it already exists).
#   4. Creates the Python virtualenv, installs dependencies, runs migrations.
#   5. Builds the frontend and runs both under pm2: "utender" (the API,
#      uvicorn) and "utender-web" (the static build, via `serve`).
#   6. Creates a demo dataset: 3 owners and 3 contractors, all approved and
#      active, plus one open project per owner. Credentials are written to
#      backend/demo-accounts.txt (readable by root only).
#
# Safe to re-run: existing .env, database and demo accounts are left alone;
# services are restarted with the current code.
#
# Optional environment variables:
#   DB_USER=app_user         MySQL user to connect as (default: app_user)
#   DB_NAME=utender_app      database name (default: utender_app; kept separate
#                            from any existing 'utender' database)
#   DB_PASSWORD=...          MySQL password, to skip the prompt
#   PUBLIC_IP=1.2.3.4        skip auto-detection of the server's public IP
#   PUBLIC_HTTP_PORT=8080    port for the web app   (default: first free from 8080)
#   PUBLIC_API_PORT=8081     port for the API       (default: first free after it)
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

step() { echo; echo -e "\033[36m==> $*\033[0m"; }
ok()   { echo -e "    \033[32m$*\033[0m"; }
warn() { echo -e "    \033[33m$*\033[0m"; }
fail() { echo; echo -e "\033[31mERROR: $*\033[0m"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run as root: sudo ./install.sh"
command -v apt-get >/dev/null 2>&1 || fail "This installer needs a Debian/Ubuntu server (apt-get)."

# ---------------------------------------------------------------- packages
step "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip build-essential libssl-dev \
    curl ca-certificates openssl pkg-config default-libmysqlclient-dev >/dev/null
if ! command -v mysql >/dev/null 2>&1; then
    apt-get install -y -qq mariadb-server mariadb-client >/dev/null
fi
systemctl enable --now mariadb >/dev/null 2>&1 || systemctl enable --now mysql >/dev/null 2>&1 \
    || fail "Could not start MySQL/MariaDB. Start your database server and re-run."
if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
fi
ok "Python $(python3 -V | cut -d' ' -f2), Node $(node -v), database client present."

# ---------------------------------------------------------------- network
step "Detecting public IP and ports"
public_ip="${PUBLIC_IP:-$(curl -fsS --max-time 5 https://api.ipify.org || true)}"
[ -n "$public_ip" ] || public_ip="localhost"
port_in_use() {
    ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"
}
find_free_port() {
    local p="$1"
    while port_in_use "$p"; do p=$((p + 1)); done
    echo "$p"
}
http_port="${PUBLIC_HTTP_PORT:-$(find_free_port 8080)}"
api_port="${PUBLIC_API_PORT:-$(find_free_port $((http_port + 1)))}"
ok "Address $public_ip, web app on $http_port, API on $api_port"

# ---------------------------------------------------------------- database
env_file="$repo_root/backend/.env"
step "Database"
db_user="${DB_USER:-app_user}"
db_name="${DB_NAME:-utender_app}"
db_password=""
if [ -f "$env_file" ] && grep -q '^DATABASE_URL=' "$env_file"; then
    ok "backend/.env already exists -- using its database settings."
else
    # The installer uses an existing MySQL/MariaDB user and never creates
    # or changes it. Its password is asked for here, or can be passed in
    # as DB_PASSWORD for unattended runs.
    if [ -z "${DB_PASSWORD:-}" ]; then
        read -r -s -p "    Password for MySQL user '${db_user}': " DB_PASSWORD < /dev/tty
        echo
    fi
    db_password="$DB_PASSWORD"
    [ -n "$db_password" ] || fail "A database password is required."
    export MYSQL_PWD="$db_password"
    mysql -h127.0.0.1 -P3306 -u"$db_user" -e "SELECT 1" >/dev/null 2>&1 \
        || fail "Could not log in as MySQL user '${db_user}' with that password."
    mysql -h127.0.0.1 -P3306 -u"$db_user" -e "CREATE DATABASE IF NOT EXISTS \`${db_name}\` CHARACTER SET utf8mb4;" \
        || fail "User '${db_user}' cannot create the '${db_name}' database. Create it and grant access, then re-run."
    unset MYSQL_PWD
    ok "Connected as '${db_user}'; database '${db_name}' is ready."
fi

# ---------------------------------------------------------------- .env
step "Configuration (backend/.env)"
new_secret() { openssl rand -hex 32; }
if [ -f "$env_file" ]; then
    ok "backend/.env already exists -- leaving it as-is."
else
    cp backend/.env.example "$env_file"
    # URL-encode the password so characters like @ or / can't break DATABASE_URL.
    db_url_password="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote_plus(sys.argv[1]))' "$db_password")"
    sed -i \
        -e "s|^DATABASE_URL=.*|DATABASE_URL=mysql+pymysql://${db_user}:${db_url_password}@127.0.0.1:3306/${db_name}|" \
        -e "s|^JWT_SECRET=.*|JWT_SECRET=$(new_secret)|" \
        -e "s|^STORAGE_SIGNING_SECRET=.*|STORAGE_SIGNING_SECRET=$(new_secret)|" \
        -e "s|^CRON_SECRET=.*|CRON_SECRET=$(new_secret)|" \
        -e "s|^STORAGE_ROOT=.*|STORAGE_ROOT=${repo_root}/backend/storage|" \
        -e "s|^APP_URL=.*|APP_URL=http://${public_ip}:${http_port}|" \
        -e "s|^API_URL=.*|API_URL=http://${public_ip}:${api_port}|" \
        -e "s|^CORS_ORIGINS=.*|CORS_ORIGINS=http://${public_ip}:${http_port}|" \
        "$env_file"
    {
        echo ""
        echo "# --- Ports (set by install.sh) ---"
        echo "PUBLIC_HTTP_PORT=${http_port}"
        echo "PUBLIC_API_PORT=${api_port}"
    } >> "$env_file"
    chmod 600 "$env_file"
    ok "Created backend/.env with generated secrets."
    warn "Stripe and email keys are blank: billing checkout and emails are skipped until you add them."
fi
http_port="$(grep -m1 '^PUBLIC_HTTP_PORT=' "$env_file" | cut -d= -f2)"
api_port="$(grep -m1 '^PUBLIC_API_PORT=' "$env_file" | cut -d= -f2)"
mkdir -p backend/storage

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "^Status: active"; then
    ufw allow "${http_port}/tcp" >/dev/null
    ufw allow "${api_port}/tcp" >/dev/null
    ok "Opened ports ${http_port} and ${api_port} in ufw."
fi

# ---------------------------------------------------------------- backend
step "Backend (Python virtualenv, migrations)"
cd "$repo_root/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/alembic upgrade head
ok "Dependencies installed, migrations applied."

step "Backend service (pm2, name: utender)"
if ! command -v pm2 >/dev/null 2>&1; then
    npm install -g --silent pm2
fi
pm2 delete utender >/dev/null 2>&1 || true
(
    cd "${repo_root}/backend"
    pm2 start "${repo_root}/backend/.venv/bin/uvicorn" --name utender --interpreter none \
        -- app.main:app --host 0.0.0.0 --port "${api_port}"
)

ready=false
for _ in $(seq 1 40); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${api_port}/docs" >/dev/null 2>&1; then ready=true; break; fi
    sleep 2
done
[ "$ready" = true ] || fail "The API did not start. Check: pm2 logs utender --lines 80"
ok "API is up on port ${api_port}."

# ---------------------------------------------------------------- demo data
step "Demo data (3 owners, 3 contractors, all approved)"
demo_file="$repo_root/backend/demo-accounts.txt"
if [ -f "$demo_file" ]; then
    ok "Demo accounts already exist (see $demo_file)."
else
    demo_password="Demo-$(openssl rand -hex 4)"
    admin_email="admin@demo.example.com"
    admin_password="Admin-$(openssl rand -hex 6)"
    .venv/bin/python scripts/create_demo_accounts.py \
        --api-url "http://127.0.0.1:${api_port}" \
        --password "$demo_password" \
        --admin-email "$admin_email" \
        --admin-password "$admin_password"
    {
        echo "U-Tender demo accounts (created by install.sh)"
        echo "App:      http://${public_ip}:${http_port}"
        echo ""
        echo "Admin:    ${admin_email}  password: ${admin_password}"
        echo "Password for all demo owners and contractors: ${demo_password}"
        echo ""
        echo "Owners:"
        echo "  owner1@demo.example.com"
        echo "  owner2@demo.example.com"
        echo "  owner3@demo.example.com"
        echo "Contractors:"
        echo "  contractor1@demo.example.com"
        echo "  contractor2@demo.example.com"
        echo "  contractor3@demo.example.com"
    } > "$demo_file"
    chmod 600 "$demo_file"
    ok "Credentials saved to $demo_file (root only)."
fi
cd "$repo_root"

# ---------------------------------------------------------------- frontend
step "Frontend (build and web service)"
cd "$repo_root/frontend"
npm install --no-audit --no-fund --silent
VITE_API_URL="http://${public_ip}:${api_port}" npm run build --silent
if ! command -v serve >/dev/null 2>&1; then
    npm install -g --silent serve
fi
serve_bin="$(command -v serve)"

pm2 delete utender-web >/dev/null 2>&1 || true
pm2 start "${serve_bin}" --name utender-web --interpreter none \
    --cwd "${repo_root}/frontend" -- -s dist -l "${http_port}"
pm2 save >/dev/null
# Start both apps again after a reboot.
pm2 startup systemd -u root --hp /root >/dev/null 2>&1 || warn "Could not register pm2 at boot; run: pm2 startup"
ok "Web app is running on port ${http_port}."

echo
echo -e "\033[36mU-Tender is installed.\033[0m"
echo "  Web app: http://${public_ip}:${http_port}"
echo "  API:     http://${public_ip}:${api_port}/docs"
echo "  Demo logins and the admin password: ${repo_root}/backend/demo-accounts.txt"
echo
echo "Useful commands:"
echo "  pm2 status                           # show utender and utender-web"
echo "  pm2 logs utender                     # API logs"
echo "  pm2 restart utender                  # restart API"
echo "  pm2 restart utender-web              # restart web app"
echo "  sudo ./install.sh                    # re-run after git pull to rebuild and restart"
