# Interface notes

The integration note captured when B first adopted C says:

```text
C response: { quality_score: number }
B reads the numeric scoring output before returning generated content.
```

The current C interface sheet says:

```text
C response: { quality_rating: number }
```

Both fields use the same numeric range. No migration note, compatibility declaration, deprecation
notice, or business identity mapping accompanies the current sheet. A's reporting requirement asks
whether historical and current evaluations are comparable under one business measure.
