# LiteLLM gateway with Notely's routing config baked in. Coolify (and other PaaS) turn a
# relative bind mount of a *file* into an empty directory on the host, which crashes LiteLLM
# ("IsADirectoryError: /etc/litellm/config.yaml"); copying the file into the image avoids that.
FROM ghcr.io/berriai/litellm:main-stable
COPY infra/litellm/config.yaml /etc/litellm/config.yaml
CMD ["--config", "/etc/litellm/config.yaml", "--port", "4000"]
