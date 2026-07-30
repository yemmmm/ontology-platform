# Interface notes

The original B/C integration records `C response: { quality_score: number }`; B reads
the numeric score before returning content. The current C interface records
`C response: { quality_rating: number }`. Both fields use the same numeric range, but
the supplied material does not itself state whether they are one business measure.
