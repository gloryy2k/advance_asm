#!/usr/bin/env bash
# Linux build adapter: the pinned framework installer assumes Homebrew/rootless.
# Versions resolved from proxy.golang.org; builds are validated on the user's Docker host.
set -euo pipefail
mkdir -p "${GOBIN:?GOBIN required}"
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@v2.17.0
go install github.com/projectdiscovery/httpx/cmd/httpx@v1.12.0
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@v3.11.1
go install github.com/projectdiscovery/dnsx/cmd/dnsx@v1.3.1
go install github.com/projectdiscovery/katana/cmd/katana@v1.8.0
go install github.com/lc/gau/v2/cmd/gau@v2.2.4
go install github.com/ffuf/ffuf/v2@v2.3.0
go install github.com/owasp-amass/amass/v4/cmd/amass@v4.2.0
go install github.com/haccer/subjack@v0.0.0-20260316055456-b53899ce6230
# Build within the main module so its replace directives are honored.
git clone --depth 1 --branch v3.99.2 https://github.com/trufflesecurity/trufflehog.git /tmp/trufflehog
(cd /tmp/trufflehog && go build -o "$GOBIN/trufflehog" .)
