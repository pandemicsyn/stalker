SHA := $(shell git rev-parse --short HEAD)
VERSION := $(shell cat VERSION)
ITTERATION := $(shell date +%s)

build:
	mkdir -p packaging/output
	mkdir -p packaging/root/usr/local/bin
	godep go build -o packaging/root/usr/local/bin/stalkerd github.com/pandemicsyn/stalker/go/stalkerd

clean:
	rm -rf packaging/output
	rm -f packaging/root/usr/local/bin/stalkerd

install:
	install -t /usr/local/bin packaging/root/usr/local/bin/stalkerd

run:
	@godep go run stalkerd/main.go

packages: clean build deb

# embeds content in go source code so that it is compiled
# and packaged inside the go binary file.
#embed:
#	rice --import-path="github.com/drone/drone/server" append --exec="packaging/root/usr/local/bin/droned"

deb:
	fpm -s dir -t deb -n stalkerd -v $(VERSION) -p packaging/output/stalkerd.deb \
		--deb-priority optional --category admin \
		--force \
		--iteration $(ITTERATION) \
		--deb-compression bzip2 \
	 	--after-install packaging/scripts/postinst.deb \
	 	--before-remove packaging/scripts/prerm.deb \
		--after-remove packaging/scripts/postrm.deb \
		--url https://github.com/pandemicsyn/stalker \
		--description "No frills scalable monitoring" \
		-m "Florian Hines <syn@ronin.io>" \
		--license "Apache License 2.0" \
		--vendor "stalker" -a amd64 \
		--config-files /etc/stalker/stalkerd.toml \
		packaging/root/=/
	cp packaging/output/stalkerd.deb packaging/output/stalkerd.deb.$(SHA)

#rpm:
#	fpm -s dir -t rpm -n drone -v $(VERSION) -p packaging/output/drone.rpm \
#		--rpm-compression bzip2 --rpm-os linux \
#		--force \
#		--iteration $(ITTERATION) \
#	 	--after-install packaging/scripts/postinst.rpm \
#	 	--before-remove packaging/scripts/prerm.rpm \
#		--after-remove packaging/scripts/postrm.rpm \
#		--url https://github.com/drone/drone \
#		--description "Drone continuous integration server" \
#		-m "Brad Rydzewski <brad@drone.io>" \
#		--license "Apache License 2.0" \
#		--vendor "drone.io" -a amd64 \
#		--config-files /etc/drone/drone.toml \
#		packaging/root/=/
