FROM docker:27-cli

RUN apk add --no-cache \
    bash \
    git \
    jq \
    nodejs \
    npm \
    python3 \
    py3-pip \
    docker-cli-compose

WORKDIR /workspace/command-center

COPY development-worker/start-worker.sh /usr/local/bin/start-worker.sh
COPY development-worker/github-askpass.sh /usr/local/bin/github-askpass.sh
RUN chmod +x /usr/local/bin/start-worker.sh /usr/local/bin/github-askpass.sh

CMD ["/usr/local/bin/start-worker.sh"]
