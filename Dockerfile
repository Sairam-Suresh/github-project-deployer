FROM docker.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	UVICORN_WORKERS=2 \
	GIT_ALLOWED_SIGNERS_FILE=/etc/git-signing/allowed_signers

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends git \
	&& rm -rf /var/lib/apt/lists/* \
	&& mkdir -p /root/.config/git /etc/git-signing \
	&& git config --global gpg.format ssh \
	&& git config --global gpg.ssh.allowedSignersFile "$GIT_ALLOWED_SIGNERS_FILE"

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
	&& pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/etc/git-signing"]

EXPOSE 2345

CMD ["python", "main.py"]

