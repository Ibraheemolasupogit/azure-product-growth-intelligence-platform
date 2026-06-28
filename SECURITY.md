# Security Policy

## Supported Status

This repository is in Milestone 1 foundation status. It is a production-style reference implementation, not a deployed production service.

## Reporting Security Issues

Open a private security advisory or contact the repository owner if you find exposed secrets, unsafe defaults, or a vulnerability in project code.

## Secret Handling

Do not commit `.env` files, credentials, keys, tokens, production telemetry, customer data, or real feedback text. Configuration examples must use placeholders and environment variable names only.

## Cloud Resources

Default tests and demos must not require live Azure credentials. Future Azure deployment paths should use managed identities, Key Vault, RBAC, and least-privilege permissions.

