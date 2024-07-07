#!/usr/bin/env bash

function show_help() {
	echo "Build Ubuntu package script"
	echo ""
	echo "Usage:"
	echo "./build_deb.sh"
	echo -e "\t-h --help"
	echo -e "\t--version='1.0.0-57624'"
	echo -e "\t--name='warp-beacon'"
	echo -e "\t--commit='06a348b6'"
	echo -e "\t--author='Sb0y'"
	echo -e "\t--email='andrey@bagrintsev.me'"
	echo ""
}

################################################################################
while [[ "${1}" != "" ]];
do
	PARAM=`echo $1 | awk -F= '{print $1}'`
	VALUE=`echo $1 | awk -F= '{print $2}'`
	case $PARAM in
		-h | --help)
			show_help
			exit 0
			;;
		--version)
			BUILD_BUILDNUMBER=`echo $VALUE | sed 's/^[^=]*=//g'`
			;;
		--commit)
			GIT_COMMIT=`echo $VALUE | sed 's/^[^=]*=//g'`
			;;
		--name)
			PACKAGE_NAME=`echo $VALUE | sed 's/^[^=]*=//g'`
			;;
		--author)
			AUTHOR=`echo $VALUE | sed 's/^[^=]*=//g'`
			;;
		--email)
			EMAIL=`echo $VALUE | sed 's/^[^=]*=//g'`
			;;
		*)
			echo "ERROR: unknown parameter \"$PARAM\""
			show_help
			exit 1
			;;
	esac
	shift
done

############################ Check enter value #################################
if [[ -z ${BUILD_BUILDNUMBER} ]];
then
	show_help
	echo -e "\nERROR: \$BUILD_BUILDNUMBER can't be empty\n"
	exit 1
fi

if [[ -z "${GIT_COMMIT}" ]];
then
	echo -e "\nERROR: \$GIT_COMMIT can't be empty\n"
	show_help
	exit 1
fi

if [[ -z "${PACKAGE_NAME}" ]];
then
	echo -e "\nERROR: \$PACKAGE_NAME can't be empty\n"
	show_help
	exit 1
fi

if [[ -z "${AUTHOR}" ]];
then
	AUTHOR='Sb0y'
fi

if [[ -z "${EMAIL}" ]];
then
	EMAIL="andrey@bagrintsev.me"
fi
################################################################################

PYT_VERSION=`echo $BUILD_BUILDNUMBER | sed 's/\-.*$//'`
DEB_VERSION=`echo $BUILD_BUILDNUMBER | sed 's/^.*\-//'`

# Set version in files
sed -i "s/%VERSION%/${PYT_VERSION}/" ${PACKAGE_NAME}/*version*.py stdeb.cfg

sed -i "s/%VERSION%/${BUILD_BUILDNUMBER}/" ${PACKAGE_NAME}/debian/control
sed -i "s/%GIT_COMMIT%/${GIT_COMMIT}/" ${PACKAGE_NAME}/debian/control

sed -i "s/%AUTHOR%/${AUTHOR}/" ${PACKAGE_NAME}/debian/control
sed -i "s/%EMAIL%/${EMAIL}/" ${PACKAGE_NAME}/debian/control

./clean.sh
python3 ./setup.py --command-packages=stdeb.command sdist_dsc --debian-version=${DEB_VERSION}

cp debian/postinst deb_dist/${PACKAGE_NAME}*/debian/
cp debian/postrm deb_dist/${PACKAGE_NAME}*/debian/
#cp debian/preinst deb_dist/${PACKAGE_NAME}*/debian/

cd deb_dist/${PACKAGE_NAME}*/
python3 -m pip install -r ../../requirements.txt
dpkg-buildpackage -rfakeroot -uc -us

exit 0
