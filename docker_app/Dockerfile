ARG BUILD_MODE

FROM ubuntu:22.04 AS base
LABEL maintainer="Andrey Bagrintsev <andrey@bagrintsev.me>"

VOLUME /var/warp_beacon

ARG TERM=xterm
ARG LC_ALL=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive 

RUN echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes 

RUN echo "deb http://us.archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse\n \
deb http://us.archive.ubuntu.com/ubuntu/ jammy-updates main restricted universe multiverse\n \
deb http://us.archive.ubuntu.com/ubuntu/ jammy-backports main restricted universe multiverse\n \
deb http://security.ubuntu.com/ubuntu jammy-security main restricted universe multiverse\n" /etc/apt/sources.list

RUN set -x \
	&& apt-get update -y \
	&& apt-get install python-is-python3 python3-pip libgl1 libglib2.0-0 -y

RUN set -x \
	&& mkdir -p /var/warp_beacon/

# Build dev image
FROM base AS image-prod
RUN set -x \
	&& python3 -m pip install warp-beacon --upgrade

# Build dev image
FROM base AS image-dev
RUN set -x \
	&& python3 -m pip install warp-beacon --upgrade \
	&& ln -sf `python3 -c 'import os, warp_beacon; print(os.path.dirname(os.path.abspath(warp_beacon.__file__)))'` /var/warp_beacon/src
VOLUME ../warp_beacon/

ENTRYPOINT [ "/usr/local/bin/warp_beacon" ]
