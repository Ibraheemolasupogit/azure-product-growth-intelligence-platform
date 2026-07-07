# Cost and Environment Assumptions

The repository has no required Azure spend. Local validation uses committed synthetic samples and standard Python tooling.

## Local Review

- No Azure subscription required.
- No Power BI license required.
- No paid APIs required.
- Runtime outputs are ignored by Git.
- Evidence artifacts are compact and deterministic.

## Future Azure Pilot Assumptions

A pilot deployment would likely use small Event Hubs throughput, ADLS Gen2 storage, scheduled Data Factory or Synapse jobs, small Azure ML compute, Power BI workspace capacity appropriate to the team, Microsoft Purview if governance scope requires it, and Azure Monitor logging with retention controls.

## Production Assumptions

Production use would require cost budgets, tagging, environment separation, private networking decisions, data-retention policy, incident support, access reviews, and FinOps ownership. Those controls are not implemented in the local repository.
