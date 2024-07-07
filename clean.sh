#!/bin/bash
python3 setup.py clean
rm -Rf deb_dist/ dist/ include/ build/ lib/ debian/.debhelper/ warp_beacon-*.tar.gz warp_beacon*.egg-info

exit 0
