# Générateur SCOPE : relit les rapports de SCOPE_ROOT (monté sur /repos, en
# lecture seule) toutes les SCOPE_INTERVAL secondes et écrit le site dans /site.
FROM python:3.12.12-slim-bookworm

RUN useradd --uid 10001 --create-home scope \
    && mkdir -p /site && chmod 0777 /site

WORKDIR /app
COPY generator/requirements.txt generator/requirements.txt
RUN pip install --no-cache-dir -r generator/requirements.txt
COPY generator/scope_gen generator/scope_gen

ENV PYTHONPATH=/app/generator \
    PYTHONUNBUFFERED=1 \
    SCOPE_ROOT=/repos \
    SCOPE_INTERVAL=3
USER scope
VOLUME ["/site"]
CMD ["python", "-m", "scope_gen", "--site", "/site", "--boucle"]
