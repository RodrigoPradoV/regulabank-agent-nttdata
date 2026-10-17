#!/usr/bin/env bash
# Despliega regulabank en el droplet `capitalfoods` bajo https://capitalfoods.studio/regulabank/ (patron de adexdatatrade).
# Uso: deploy/deploy_droplet.sh RELEASE_DIR      (release = chunks, entities, mentions, edges, conflicts .parquet + lancedb/, con vectores de OpenAI)
# Cada paso verifica antes de seguir; el nginx se prueba con `nginx -t` y se recarga (nunca se reinicia) y, si falla, se restaura la copia.
set -euo pipefail
RELEASE="${1:?falta el directorio del release}"
H=capitalfoods
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE=/etc/nginx/sites-enabled/capitalfoods

echo "== 1. espacio y memoria en el droplet"
ssh $H 'df -h / | tail -1; free -m | sed -n 2p; test "$(df --output=avail -BG / | tail -1 | tr -dc 0-9)" -ge 8'

echo "== 2. frontend (base-href /regulabank/)"
( cd "$ROOT/frontend" && npx ng build --base-href /regulabank/ >/dev/null )
ssh $H 'mkdir -p /var/www/regulabank /opt/regulabank/backend /opt/regulabank/release /var/log/regulabank'
rsync -az --delete "$ROOT/frontend/dist/ui/browser/" $H:/var/www/regulabank/

echo "== 3. backend y release"
rsync -az --delete --exclude .venv --exclude __pycache__ --exclude tests --exclude '*.egg-info' --exclude 'seeds/synthetic' "$ROOT/backend/" $H:/opt/regulabank/backend/
rsync -az --delete --exclude ledger.jsonl --exclude llm-cache "$RELEASE/" $H:/opt/regulabank/release/

echo "== 4. entorno (sin torch: los embeddings salen de la API de OpenAI)"
ssh $H 'test -d /opt/regulabank/venv || python3 -m venv /opt/regulabank/venv; /opt/regulabank/venv/bin/pip install -q --upgrade pip; /opt/regulabank/venv/bin/pip install -q -e /opt/regulabank/backend'
ssh $H 'test -f /etc/regulabank.env || { umask 077; printf "REGULABANK_RELEASE=/opt/regulabank/release\nMODEL_PROVIDER=openai\nEMBED_MODEL=openai:text-embedding-3-small\n" > /etc/regulabank.env; }'
ssh $H 'grep -q ^OPENAI_API_KEY= /etc/regulabank.env' || { echo "FALTA OPENAI_API_KEY en /etc/regulabank.env (ver README de deploy)"; exit 3; }

echo "== 5. servicio"
scp -q "$ROOT/deploy/regulabank-api.service" $H:/etc/systemd/system/regulabank-api.service
ssh $H 'systemctl daemon-reload && systemctl enable --now regulabank-api && sleep 8 && systemctl is-active regulabank-api && curl -sf http://127.0.0.1:3320/health'

echo "== 6. nginx (copia de seguridad, prueba y recarga)"
scp -q "$ROOT/deploy/nginx-regulabank.conf" $H:/tmp/nginx-regulabank.conf
ssh $H "set -e; grep -q '# regulabank:' $SITE || { cp $SITE $SITE.bak-regulabank; python3 - <<'PY'
import re
s=open('$SITE').read(); block=open('/tmp/nginx-regulabank.conf').read()
marker='  # adexdatatrade:'
assert marker in s, 'no encuentro el bloque de adexdatatrade para insertar antes'
open('$SITE','w').write(s.replace(marker, block+'\n'+marker,1))
PY
}; nginx -t && systemctl reload nginx || { cp $SITE.bak-regulabank $SITE; nginx -t && systemctl reload nginx; echo 'nginx fallo: restaurado'; exit 4; }"

echo "== 7. verificacion publica"
curl -sf -o /dev/null -w "pagina %{http_code}\n" https://capitalfoods.studio/regulabank/
curl -sf https://capitalfoods.studio/regulabank/api/health; echo
curl -s -o /dev/null -w "adexdatatrade sigue en %{http_code}\n" https://capitalfoods.studio/adexdatatrade/
