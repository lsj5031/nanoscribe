.PHONY: build shell run smoke clean help

.DEFAULT_GOAL := help

IMAGE ?= funasr
BASE_IMAGE ?= glm-asr-glm-asr:latest

help:
	@echo "FunASR Docker Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "  build   Build the derived FunASR image"
	@echo "  shell   Open an interactive shell with GPU and caches mounted"
	@echo "  run     Run a one-shot FunASR readiness check"
	@echo "  smoke   Verify funasr and modelscope imports"
	@echo "  clean   Remove the built image"

build:
	docker build --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE) .

shell:
	docker run --rm -it --gpus all \
		-v $(HOME)/.cache/huggingface:/home/appuser/.cache/huggingface \
		-v $(HOME)/.cache/modelscope:/home/appuser/.cache/modelscope \
		-v $(CURDIR)/data:/app/data \
		$(IMAGE) /bin/bash

run:
	docker run --rm --gpus all \
		-v $(HOME)/.cache/huggingface:/home/appuser/.cache/huggingface \
		-v $(HOME)/.cache/modelscope:/home/appuser/.cache/modelscope \
		-v $(CURDIR)/data:/app/data \
		$(IMAGE)

smoke:
	docker run --rm $(IMAGE) python -c "import funasr, modelscope; print('ok')"

clean:
	docker rmi $(IMAGE) || true
