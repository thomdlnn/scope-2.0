# Générateur SCOPE : régénère le site toutes les SCOPE_INTERVAL secondes dans /site.
FROM python:3.12.12-slim-bookworm

# git : utile au mode --local (clones montés dans le conteneur).
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home scope \
    && git config --system --add safe.directory "*" \
    && mkdir -p /site /projects && chown scope:scope /site

WORKDIR /app
COPY generator/requirements.txt generator/requirements.txt
RUN pip install --no-cache-dir -r generator/requirements.txt
COPY generator/scope_gen generator/scope_gen
COPY docker/entrypoint.sh /usr/local/bin/scope-entrypoint

ENV PYTHONPATH=/app/generator \
    PYTHONUNBUFFERED=1 \
    SCOPE_INTERVAL=900
USER scope
VOLUME ["/site"]
ENTRYPOINT ["scope-entrypoint"]
CMD ["loop"]
