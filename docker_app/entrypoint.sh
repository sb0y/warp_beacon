#!/bin/bash

if [[ -f /init_accounts.json ]];
then
	mv -f /init_accounts.json /var/warp_beacon/accounts.json
fi

if [[ -f /init_proxies.json ]];
then
	mv -f /init_proxies.json /var/warp_beacon/proxies.json
fi

exec /usr/local/bin/warp_beacon