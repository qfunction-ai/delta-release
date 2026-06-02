FROM pgvector/pgvector:pg16

# Bake init scripts into the image instead of bind-mounting.
# This avoids CRLF issues on Windows (core.autocrlf=true converts LF
# to CRLF on checkout, breaking shell scripts in Linux containers).
# dos2unix ensures the scripts work regardless of host line endings.
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix && rm -rf /var/lib/apt/lists/*
COPY initdb/ /docker-entrypoint-initdb.d/
RUN dos2unix /docker-entrypoint-initdb.d/*.sh && chmod +x /docker-entrypoint-initdb.d/*.sh
