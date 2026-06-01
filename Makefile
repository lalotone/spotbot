IMAGE ?= spotbot
TAG   ?= latest

# Register QEMU binfmt handlers for cross-arch emulation
.PHONY: qemu
qemu:
	docker run --rm --privileged tonistiigi/binfmt --install all

# Native platform (default)
.PHONY: build
build:
	docker build -t $(IMAGE):$(TAG) .

# Explicit amd64
.PHONY: build-amd64
build-amd64: qemu
	docker buildx build --platform linux/amd64 -t $(IMAGE):$(TAG)-amd64 .

# ARM64 (Raspberry Pi 4/5 running 64-bit OS)
.PHONY: build-arm64
build-arm64: qemu
	docker buildx build --platform linux/arm64 -t $(IMAGE):$(TAG)-arm64 .

# ARM v7 (Raspberry Pi 2/3 running 32-bit OS)
.PHONY: build-armv7
build-armv7: qemu
	docker buildx build --platform linux/arm/v7 -t $(IMAGE):$(TAG)-armv7 .

# Multi-arch manifest (amd64 + arm64 + armv7)
.PHONY: build-multi
build-multi: qemu
	docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t $(IMAGE):$(TAG) .

# Push multi-arch image (requires registry login)
.PHONY: push
push: qemu
	docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t $(IMAGE):$(TAG) --push .

.PHONY: clean
clean:
	docker rmi -f $(IMAGE):$(TAG) $(IMAGE):$(TAG)-amd64 $(IMAGE):$(TAG)-arm64 $(IMAGE):$(TAG)-armv7 2>/dev/null || true
