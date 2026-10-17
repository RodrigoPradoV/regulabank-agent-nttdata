# Job de GPU en RunPod: GLiNER2 + embeddings sobre `chunks.parquet`

`job.py` lee `chunks.parquet` (esquema `schema.CHUNKS`, 25 columnas), corre GLiNER2 (`fastino/gliner2-large-v1`,
etiquetas de `regulabank/graphs/gliner2.py`, umbral 0,3, ventanas de 384 palabras con solape de 64) y el modelo de
embedding (`google/embeddinggemma-300m` con prefijo `title: {norm_short}, art. {article_no} | text: `; si gemma esta
cerrado cae a `intfloat/multilingual-e5-small` con prefijo `passage: ` y lo deja escrito en el manifiesto) y escribe:

```
out/mentions_gliner2.parquet   schema.MENTIONS, method = gliner2, text[start:end] == mention verificado
out/vectors.parquet            chunk_id, model, dim, vector list<float32>
out/manifest.json              tiempos, modelos, repuesto usado, sha256 del chunks.parquet
out/DONE                       solo cuando todo termino
out/parts/                     lotes atomicos (gliner2.NNNNN.parquet, embed.NNNNN.parquet) para reanudar
```

Reglas (lecciones pagadas con horas de pod): aborta sin CUDA salvo `--allow-cpu`; `--preflight` antes de la corrida
completa; lotes atomicos y reanudables (`skip` de los chunk_id ya hechos); una linea de avance por lote; borrar el pod
al terminar.

## 0. Humo en la Mac (sin pod)

```bash
cd backend
uv pip install -e ".[models]" --python .venv/bin/python
.venv/bin/python pod/job.py --chunks ../data/releases/r0001/chunks.parquet --out /tmp/pod-smoke --limit 20 --allow-cpu
```

## 1. Crear el pod

Plantilla PyTorch de RunPod (CUDA 12.x), una GPU de 16 a 24 GB (RTX A5000 / L4 / RTX 4090 bastan: gliner2-large
pesa ~1,8 GB y gemma-300m ~1,2 GB), disco de contenedor >= 20 GB, con llave SSH cargada en la cuenta. Anotar el
`POD_ID` y la IP/puerto SSH publicos del panel.

```bash
runpodctl config --apiKey "$RUNPOD_API_KEY"
runpodctl get pod            # POD_ID, estado, GPU
```

## 2. Subir `chunks.parquet` y el repo

Opcion A, `runpodctl send/receive` (sin SSH; un codigo de un solo uso por archivo):

```bash
# en la Mac
tar czf regulabank-backend.tgz -C backend --exclude .venv --exclude '__pycache__' .
runpodctl send regulabank-backend.tgz      # imprime: runpodctl receive <CODE>
runpodctl send data/releases/r0001/chunks.parquet
# en el pod (terminal web o ssh)
mkdir -p /workspace/regulabank && cd /workspace/regulabank
runpodctl receive <CODE-del-tgz> && tar xzf regulabank-backend.tgz && rm regulabank-backend.tgz
runpodctl receive <CODE-del-parquet>
```

Opcion B, `scp` por el proxy SSH de RunPod (IP y puerto del panel, usuario `root`):

```bash
scp -P <PORT> -i ~/.ssh/id_ed25519 data/releases/r0001/chunks.parquet root@<IP>:/workspace/regulabank/
rsync -avz -e "ssh -p <PORT> -i ~/.ssh/id_ed25519" --exclude .venv --exclude __pycache__ backend/ root@<IP>:/workspace/regulabank/
```

## 3. Instalar en el pod

```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519 root@<IP>
cd /workspace/regulabank
pip install uv
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[models]"            # gliner2, sentence-transformers, torch (la imagen ya trae torch CUDA)
# si la imagen no trae torch con CUDA: uv pip install torch --index-url https://download.pytorch.org/whl/cu124
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# gemma es gated: hf auth login --token "$HF_TOKEN"   (si no, el job cae solo a multilingual-e5-small)
```

## 4. Preflight (obligatorio antes de la corrida completa)

```bash
python pod/job.py --chunks chunks.parquet --out out --preflight
```

Imprime segundos por chunk de cada modelo (sobre 2 chunks reales y el mas largo) y el total proyectado. Si la
proyeccion no cabe en el presupuesto, no seguir.

## 5. Corrida completa (desacoplada de la sesion SSH)

```bash
nohup python pod/job.py --chunks chunks.parquet --out out > job.log 2>&1 &
tail -f job.log                      # una linea por lote: [gliner2] 128/195 chunks | 240.0 chunks/min | ...
ls out/DONE                          # existe solo cuando termino todo
```

Si el pod se reinicia o el proceso muere, relanzar el mismo comando: salta los chunk_id que ya estan en `out/parts/`.
Vigilar el avance (el contador de `job.log`), no la existencia del proceso.

## 6. Bajar `out/`

```bash
# en el pod
tar czf out.tgz out && runpodctl send out.tgz
# en la Mac
runpodctl receive <CODE>
mkdir -p data/pod/r0001 && tar xzf out.tgz -C data/pod/r0001 && rm out.tgz
# o por scp: scp -P <PORT> -i ~/.ssh/id_ed25519 -r root@<IP>:/workspace/regulabank/out data/pod/r0001/
```

Luego, en la Mac:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m regulabank.graphs build --release data/releases/r0001 --pod-out data/pod/r0001/out --load
```

## 7. BORRAR EL POD

Un pod vivo sin trabajar cobra por hora (21 h de una vez). Al tener `out/` en la Mac:

```bash
runpodctl remove pod <POD_ID>
runpodctl get pod            # debe quedar vacio
```
