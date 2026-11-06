# oss-fw-ci containers; every repository command runs in one of them
# (scripts/in-container.sh), on the CIL runners and on a lease alike.
#   control  (--target control)  resolve, submit, monitor, collect,
#            publish and the unit tests: git, curl, b4, Python with the
#            run document and LAVA client deps. Small: the arm64 2c runners
#            build it.
#   build    (--target build)    TF-A, OP-TEE, U-Boot, Linux, the ESP and
#            the package: the kernel.org GCC 14.2.0 aarch64 toolchain (as
#            u-boot-ci and upstream U-Boot CI), qcom-ptool, ukify with the
#            arm64 systemd-boot stub, qtestsign's Python deps.
#   rootfs   (--target rootfs)   qcom-buildroot's own build (repo, the
#            OP-TEE build prerequisites, host ffmpeg for the video streams,
#            the libraries the QAIRT converters need: x86_64 only).
FROM ubuntu:noble-20251013 AS control
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates curl git python3 python3-venv \
	&& rm -rf /var/lib/apt/lists/*
COPY requirements-control.txt /tmp/requirements-control.txt
RUN python3 -m venv /opt/venv \
	&& /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-control.txt \
	&& rm /tmp/requirements-control.txt
ENV PATH=/opt/venv/bin:$PATH HOME=/tmp/home
RUN mkdir -m 1777 /tmp/home && git config --system --add safe.directory '*'
WORKDIR /work

FROM control AS build
ARG TCVER=14.2.0
RUN apt-get update && apt-get install -y --no-install-recommends \
	bc bison build-essential bzip2 cpio device-tree-compiler dosfstools \
	e2fsprogs file flex gdisk kmod libelf-dev libgnutls28-dev libssl-dev \
	lz4 make mtools openssl patch perl python-is-python3 python3-dev \
	python3-pyelftools python3-cryptography rsync swig systemd-ukify \
	unzip uuid-dev wget xxd xz-utils zstd \
	&& rm -rf /var/lib/apt/lists/*
RUN host=$([ "$(dpkg --print-architecture)" = arm64 ] && echo arm64 || echo x86_64) \
	&& wget -qO- https://mirrors.edge.kernel.org/pub/tools/crosstool/files/bin/$host/${TCVER}/$host-gcc-${TCVER}-nolibc-aarch64-linux.tar.xz \
	| tar -C /opt -xJ
ENV PATH=/opt/gcc-${TCVER}-nolibc/aarch64-linux/bin:$PATH CROSS_COMPILE=aarch64-linux-
# The aarch64 systemd-boot stub for ukify (noble amd64 ships only x86's).
RUN if [ "$(dpkg --print-architecture)" = arm64 ]; then \
		apt-get update && apt-get install -y --no-install-recommends systemd-boot-efi; \
	else \
		dpkg --add-architecture arm64 \
		&& sed -i 's/^Types: deb$/Types: deb\nArchitectures: amd64/' /etc/apt/sources.list.d/ubuntu.sources \
		&& printf 'Types: deb\nURIs: http://ports.ubuntu.com/ubuntu-ports\nSuites: noble noble-updates\nComponents: main universe\nArchitectures: arm64\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' \
			> /etc/apt/sources.list.d/ports.sources \
		&& apt-get update && cd /tmp && apt-get download systemd-boot-efi:arm64 \
		&& dpkg-deb -x systemd-boot-efi_*_arm64.deb /tmp/sdboot \
		&& install -D -m 0644 /tmp/sdboot/usr/lib/systemd/boot/efi/linuxaa64.efi.stub \
			/usr/lib/systemd/boot/efi/linuxaa64.efi.stub \
		&& rm -rf /tmp/sdboot /tmp/*.deb; \
	fi \
	&& test -f /usr/lib/systemd/boot/efi/linuxaa64.efi.stub \
	&& rm -rf /var/lib/apt/lists/*
ARG QCOM_PTOOL_REV=c6c8fec1139a83e66f62c5cf05d341cc51db13e4
COPY requirements-build.txt /tmp/requirements-build.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-build.txt \
	&& git clone -q https://github.com/qualcomm-linux/qcom-ptool /opt/qcom-ptool \
	&& git -C /opt/qcom-ptool checkout -q ${QCOM_PTOOL_REV} \
	&& /opt/venv/bin/pip install --no-cache-dir /opt/qcom-ptool \
	&& rm /tmp/requirements-build.txt

FROM ubuntu:noble-20251013 AS rootfs
ENV DEBIAN_FRONTEND=noninteractive
# OP-TEE build prerequisites (optee docs, as qcom-buildroot's README),
# plus ffmpeg (video streams) and the QAIRT converter libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
	acpica-tools adb autoconf automake bc bison build-essential ccache cpio \
	cscope curl device-tree-compiler e2tools expect fastboot file flex \
	ftp-upload gdisk git libattr1-dev libcap-ng-dev libfdt-dev libftdi-dev \
	libglib2.0-dev libgmp3-dev libhidapi-dev libmpc-dev libncurses5-dev \
	libpixman-1-dev libslirp-dev libssl-dev libtool libusb-1.0-0-dev make \
	mtools netcat-openbsd ninja-build python3-cryptography python3-pip \
	python3-pyelftools python3-serial python-is-python3 rsync swig unzip \
	uuid-dev wget xdg-utils xterm xz-utils zlib1g-dev ca-certificates \
	ffmpeg libc++1 libc++abi1 libatomic1 repo dosfstools e2fsprogs zstd \
	systemd-ukify locales python3-yaml \
	&& sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen \
	&& rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 HOME=/tmp/home
RUN mkdir -m 1777 /tmp/home && git config --system --add safe.directory '*' \
	&& git config --system user.name ossci && git config --system user.email ossci@localhost
WORKDIR /work
