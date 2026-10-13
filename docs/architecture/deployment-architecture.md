# Deployment architecture

Target compose stack (see root `docker-compose.yml`):

```text
reverse-proxy → frontend, backend
backend → postgres, redis, ml-api
ml-api → postgres (index tables), model cache volume
```

Production hardening (TLS, secrets, scaling) is out of REPO-STRUCTURE-V1 scope.
