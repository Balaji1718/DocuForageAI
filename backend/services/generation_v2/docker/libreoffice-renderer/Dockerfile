FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Pinned package set for canonical render environment.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice=1:7.3.7-0ubuntu0.22.04.10 \
    libreoffice-writer=1:7.3.7-0ubuntu0.22.04.10 \
    fonts-dejavu-core=2.37-2build1 \
    fonts-liberation=1:1.07.4-11 \
    fonts-noto-core=20201225-1build1 \
    ca-certificates=20240203~22.04.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

ENTRYPOINT ["/usr/bin/soffice"]
