# Infrastructure Skeletons

This folder contains documentation-grade infrastructure notes only. It does not include executable deployment workflows, subscription IDs, tenant IDs, service principals, secrets, or commands that create Azure resources.

## Folders

- `bicep/`: intended Azure resource outline for a future Bicep implementation.
- `terraform/`: intended Azure resource outline for a future Terraform implementation.

## Safety Boundary

No GitHub Actions deployment job is configured. No `az deployment` or `terraform apply` command is required by this repository. Any future live deployment should be implemented in a separate reviewed change with environment, identity, networking, security, cost, and operations approval.
