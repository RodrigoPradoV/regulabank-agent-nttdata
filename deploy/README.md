# Despliegue en el droplet `capitalfoods`

Publica regulabank en https://capitalfoods.studio/regulabank/, público y sin login (mismo patrón que adexdatatrade).

| Pieza | Dónde |
|---|---|
| Frontend estático (build con `--base-href /regulabank/`) | `/var/www/regulabank` |
| Backend (FastAPI + agente) | `/opt/regulabank/backend`, venv en `/opt/regulabank/venv`, sin torch |
| Release (Parquet + LanceDB con vectores de OpenAI) | `/opt/regulabank/release` |
| Servicio | `regulabank-api.service` en 127.0.0.1:3320, `MemoryMax=900M` |
| nginx | tres bloques insertados antes del de adexdatatrade en `/etc/nginx/sites-enabled/capitalfoods` |
| Secretos | `/etc/regulabank.env` (0600): `OPENAI_API_KEY`, `MODEL_PROVIDER`, `EMBED_MODEL`, `REGULABANK_RELEASE` |

## Desplegar o actualizar

```bash
deploy/deploy_droplet.sh RELEASE_DIR      # el script se puede repetir: rsync incremental y nginx -t antes de recargar
```

La clave no la copia el script. Se pone una vez, desde la Mac, sin imprimirla:

```bash
security find-generic-password -s lumen-openai -w | ssh capitalfoods 'umask 077; k=$(cat); grep -v ^OPENAI_API_KEY= /etc/regulabank.env > /tmp/rb.env; printf "OPENAI_API_KEY=%s\n" "$k" >> /tmp/rb.env; mv /tmp/rb.env /etc/regulabank.env; chmod 600 /etc/regulabank.env'
```

Después se vuelve a correr el script (arranca el servicio y verifica).

## Por qué embeddings de OpenAI y no gemma en el servidor

El droplet tiene 4 GB de RAM con ~1,8 GB libres y corre el ERP de capitalfoods. `embeddinggemma-300m` con torch ocupa más de 1,2 GB.
Con `text-embedding-3-small` el retrieval empata en el golden (nDCG@8 0,582 vs 0,563 en desarrollo; 0,623 en reservado en ambos).

## Sacarlo

Borrar los tres bloques `# regulabank:` del sitio, `systemctl disable --now regulabank-api`, y `/opt/regulabank`, `/var/www/regulabank`, `/etc/regulabank.env`.
