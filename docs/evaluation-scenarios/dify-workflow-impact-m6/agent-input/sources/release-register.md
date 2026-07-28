# Workflow C release register

Workflow C has the following recorded states:

| State | Publication status | Output shown in the release record |
| --- | --- | --- |
| Current Draft | not callable by other workflows | `quality_rating:number` |
| Version 1 | published | `quality_score:number` |
| Version 2 | published and marked latest | `quality_rating:number` |

Publication makes a workflow version available for Tool use. The release register does not record a
deployment event for B after Version 2 was published. B's tool configuration continues to identify C
only by workflow identity.
