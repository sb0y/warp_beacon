FROM ubuntu:22.04
LABEL maintainer="Andrey Bagrintsev <andrey@bagrintsev.me>"

VOLUME /var/warp_beacon

ARG TERM=xterm
ARG LC_ALL=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive 

RUN echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes 

RUN echo "deb http://us.archive.ubuntu.com/ubuntu/ focal main restricted universe multiverse\n \
deb http://us.archive.ubuntu.com/ubuntu/ focal-updates main restricted universe multiverse\n \
deb http://us.archive.ubuntu.com/ubuntu/ focal-backports main restricted universe multiverse\n \
deb http://security.ubuntu.com/ubuntu focal-security main restricted universe multiverse\n" /etc/apt/sources.list

RUN set -x \
	&& apt-get install python-is-python3 -y

RUN mkdir -p /var/warp_beacon

WORKDIR /warp_beacon

COPY ./entrypoint.sh .

ENTRYPOINT [ "./entrypoint.sh" ]