# Security Policy

## Reporting a vulnerability

Please report security issues privately to the repository maintainer. Do not open public issues for credential leaks or exploitable bugs.

## Secrets

- **Never commit `.env`** — it is gitignored and holds your Firebase database secret
- Use [`.env.example`](.env.example) as a template only
- Rotate your Firebase database secret if it is ever exposed

## Firebase authentication

This project uses the legacy Firebase Realtime Database secret (`?auth=` query parameter). Google recommends migrating to Firebase Authentication or service accounts. See [Google's deprecation notice](https://firebase.google.com/docs/database/rest/auth) when planning production deployments.

RTDB security rules should restrict access to required paths. See [docs/firebase-schema.md](docs/firebase-schema.md#security-rules).

## Pi deployment

- Run the daemon as a dedicated user (`pi` or a service account)
- Restrict RTDB security rules to the minimum paths required
- Keep the Pi OS and Python dependencies updated
- Review hardening in [`deploy/maxxair-fan.service`](deploy/maxxair-fan.service)

## Related

- [Configuration](docs/configuration.md)
- [Troubleshooting → Firebase errors](docs/troubleshooting.md#firebase-401--connection-errors)
