# Power BI Refresh Plan

1. Rebuild reporting CSVs from committed or certified analytics evidence.
2. Compare `reporting-manifest.json` checksums with the promoted artifact set.
3. Publish CSV outputs to the future ADLS Gen2 curated reporting zone.
4. Refresh the Power BI semantic model from certified reporting tables.
5. Review diagnostics, lineage, and synthetic-data disclaimers before promotion.

This repository does not deploy Power BI, Fabric, Azure Data Factory, or Azure resources.
