# DocKG Embedder Benchmark Report

- Started (UTC): 2026-04-22T23:59:57.823230+00:00
- Completed (UTC): 2026-04-23T00:13:22.691297+00:00
- Models: `all-mpnet-base-v2`, `BAAI/bge-small-en-v1.5`, `all-MiniLM-L6-v2`
- Top-N captured: 5

## Cross-Book Score Summary (mean cosine similarity)

| Model | Book | justice and morality | revenge and obsession | love and social class | fate and hubris | identity and freedom |
|---|---|---:|---:|---:|---:|---:|
| `all-mpnet-base-v2` | Adventures of Huckleberry Finn | 0.005 | 0.000 | 0.000 | 0.000 | 0.000 |
| `BAAI/bge-small-en-v1.5` | Adventures of Huckleberry Finn | 0.440 | 0.354 | 0.308 | 0.290 | 0.330 |
| `all-MiniLM-L6-v2` | Adventures of Huckleberry Finn | 0.001 | 0.000 | 0.000 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | The Odyssey | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `BAAI/bge-small-en-v1.5` | The Odyssey | 0.403 | 0.349 | 0.329 | 0.284 | 0.320 |
| `all-MiniLM-L6-v2` | The Odyssey | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | Pride and Prejudice | 0.010 | 0.059 | 0.000 | 0.000 | 0.000 |
| `BAAI/bge-small-en-v1.5` | Pride and Prejudice | 0.482 | 0.366 | 0.429 | 0.278 | 0.340 |
| `all-MiniLM-L6-v2` | Pride and Prejudice | 0.000 | 0.086 | 0.025 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | Les Miserables | 0.123 | 0.138 | 0.000 | 0.032 | 0.007 |
| `BAAI/bge-small-en-v1.5` | Les Miserables | 0.503 | 0.473 | 0.429 | 0.327 | 0.401 |
| `all-MiniLM-L6-v2` | Les Miserables | 0.039 | 0.029 | 0.000 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | Crime and Punishment | 0.237 | 0.090 | 0.063 | 0.059 | 0.000 |
| `BAAI/bge-small-en-v1.5` | Crime and Punishment | 0.514 | 0.450 | 0.465 | 0.306 | 0.430 |
| `all-MiniLM-L6-v2` | Crime and Punishment | 0.143 | 0.016 | 0.061 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | Beyond Good and Evil | 0.188 | 0.112 | 0.000 | 0.169 | 0.004 |
| `BAAI/bge-small-en-v1.5` | Beyond Good and Evil | 0.536 | 0.429 | 0.390 | 0.290 | 0.449 |
| `all-MiniLM-L6-v2` | Beyond Good and Evil | 0.262 | 0.067 | 0.000 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | Hamlet | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `BAAI/bge-small-en-v1.5` | Hamlet | 0.470 | 0.372 | 0.395 | 0.291 | 0.340 |
| `all-MiniLM-L6-v2` | Hamlet | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `all-mpnet-base-v2` | Don Quixote | 0.017 | 0.022 | 0.032 | 0.073 | 0.000 |
| `BAAI/bge-small-en-v1.5` | Don Quixote | 0.489 | 0.381 | 0.443 | 0.276 | 0.421 |
| `all-MiniLM-L6-v2` | Don Quixote | 0.006 | 0.005 | 0.053 | 0.000 | 0.000 |

## Book: Adventures of Huckleberry Finn

### Model: `all-mpnet-base-v2`
- Build: 14.1s, 4419 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 80ms
- mean_score=0.0050  mean_dist=1.0347  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | moral | 0.0126 | 0.9874 | 0 |
| 2 | chunk | chunk:1147 | 0.0126 | 0.9874 | 1 |
| 3 | topic | topic:ain_moral | 0.0000 | 1.0066 | 0 |
| 4 | chunk | chunk:0131 | 0.0000 | 1.0961 | 0 |
| 5 | entity | That | 0.0000 | 1.0961 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 48ms
- mean_score=0.0000  mean_dist=1.2481  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Despised | 0.0000 | 1.1655 | 0 |
| 2 | chunk | chunk:0479 | 0.0000 | 1.1655 | 1 |
| 3 | keyword | abusive | 0.0000 | 1.2879 | 0 |
| 4 | chunk | chunk:0005 | 0.0000 | 1.2879 | 1 |
| 5 | chunk | chunk:0341 | 0.0000 | 1.3335 | 0 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 43ms
- mean_score=0.0000  mean_dist=1.2523  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | love | 0.0000 | 1.1875 | 0 |
| 2 | chunk | chunk:0884 | 0.0000 | 1.1875 | 1 |
| 3 | keyword | acquainted | 0.0000 | 1.2713 | 0 |
| 4 | chunk | chunk:1089 | 0.0000 | 1.2713 | 1 |
| 5 | keyword | harem | 0.0000 | 1.3439 | 0 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 29ms
- mean_score=0.0000  mean_dist=1.1195  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0678 | 0.0000 | 1.1195 | 0 |
| 2 | chunk | chunk:0677 | 0.0000 | 1.1195 | 1 |
| 3 | chunk | chunk:0679 | 0.0000 | 1.1195 | 1 |
| 4 | section | CHAPTER XXII. | 0.0000 | 1.1195 | 1 |
| 5 | entity | North | 0.0000 | 1.1195 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 29ms
- mean_score=0.0000  mean_dist=1.3668  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Conscience | 0.0000 | 1.3617 | 0 |
| 2 | chunk | chunk:0414 | 0.0000 | 1.3617 | 1 |
| 3 | topic | topic:ain_moral | 0.0000 | 1.3670 | 0 |
| 4 | chunk | chunk:1147 | 0.0000 | 1.3670 | 1 |
| 5 | keyword | myself | 0.0000 | 1.3764 | 0 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 9.3s, 4419 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 128ms
- mean_score=0.4399  mean_dist=0.5601  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | moral | 0.4960 | 0.5040 | 0 |
| 2 | topic | topic:ain_moral | 0.4727 | 0.5273 | 0 |
| 3 | topic | topic:him_judge | 0.4118 | 0.5882 | 0 |
| 4 | chunk | chunk:0105 | 0.4095 | 0.5905 | 0 |
| 5 | chunk | chunk:1230 | 0.4095 | 0.5905 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 102ms
- mean_score=0.3541  mean_dist=0.6459  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Despised | 0.3961 | 0.6039 | 0 |
| 2 | chunk | chunk:0479 | 0.3961 | 0.6039 | 1 |
| 3 | chunk | chunk:0341 | 0.3261 | 0.6739 | 0 |
| 4 | chunk | chunk:1148 | 0.3261 | 0.6739 | 1 |
| 5 | chunk | chunk:0828 | 0.3261 | 0.6739 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 116ms
- mean_score=0.3083  mean_dist=0.6917  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | love | 0.3722 | 0.6278 | 0 |
| 2 | chunk | chunk:0884 | 0.3722 | 0.6278 | 1 |
| 3 | topic | topic:because_orgies | 0.2661 | 0.7339 | 0 |
| 4 | keyword | feelings | 0.2655 | 0.7345 | 0 |
| 5 | chunk | chunk:0789 | 0.2655 | 0.7345 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 90ms
- mean_score=0.2899  mean_dist=0.7101  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | fate | 0.3018 | 0.6982 | 0 |
| 2 | chunk | chunk:0591 | 0.3018 | 0.6982 | 1 |
| 3 | chunk | chunk:0874 | 0.2819 | 0.7181 | 0 |
| 4 | chunk | chunk:0561 | 0.2819 | 0.7181 | 1 |
| 5 | chunk | chunk:0486 | 0.2819 | 0.7181 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 86ms
- mean_score=0.3298  mean_dist=0.6702  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | myself | 0.3298 | 0.6702 | 0 |
| 2 | chunk | chunk:0561 | 0.3298 | 0.6702 | 1 |
| 3 | chunk | chunk:0341 | 0.3298 | 0.6702 | 1 |
| 4 | chunk | chunk:0415 | 0.3298 | 0.6702 | 1 |
| 5 | chunk | chunk:0812 | 0.3298 | 0.6702 | 1 |

### Model: `all-MiniLM-L6-v2`
- Build: 2.4s, 4419 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 142ms
- mean_score=0.0011  mean_dist=1.1446  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:ain_moral | 0.0057 | 0.9943 | 0 |
| 2 | keyword | moral | 0.0000 | 1.0382 | 0 |
| 3 | chunk | chunk:0567 | 0.0000 | 1.2302 | 0 |
| 4 | chunk | chunk:0001 | 0.0000 | 1.2302 | 1 |
| 5 | chunk | chunk:1228 | 0.0000 | 1.2302 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 91ms
- mean_score=0.0000  mean_dist=1.2385  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Despised | 0.0000 | 1.1184 | 0 |
| 2 | chunk | chunk:0479 | 0.0000 | 1.1184 | 1 |
| 3 | chunk | chunk:0567 | 0.0000 | 1.3186 | 0 |
| 4 | chunk | chunk:0001 | 0.0000 | 1.3186 | 1 |
| 5 | chunk | chunk:1141 | 0.0000 | 1.3186 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 103ms
- mean_score=0.0000  mean_dist=1.2547  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | love | 0.0000 | 1.1207 | 0 |
| 2 | chunk | chunk:0884 | 0.0000 | 1.1207 | 1 |
| 3 | keyword | moral | 0.0000 | 1.3378 | 0 |
| 4 | chunk | chunk:1147 | 0.0000 | 1.3378 | 1 |
| 5 | keyword | juliet | 0.0000 | 1.3563 | 0 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 84ms
- mean_score=0.0000  mean_dist=1.3193  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | fate | 0.0000 | 1.2520 | 0 |
| 2 | chunk | chunk:0591 | 0.0000 | 1.2520 | 1 |
| 3 | keyword | betray | 0.0000 | 1.3628 | 0 |
| 4 | chunk | chunk:1257 | 0.0000 | 1.3628 | 1 |
| 5 | entity | Hamlet | 0.0000 | 1.3668 | 0 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 120ms
- mean_score=0.0000  mean_dist=1.2643  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | myself | 0.0000 | 1.2643 | 0 |
| 2 | chunk | chunk:0341 | 0.0000 | 1.2643 | 1 |
| 3 | chunk | chunk:0812 | 0.0000 | 1.2643 | 1 |
| 4 | chunk | chunk:0951 | 0.0000 | 1.2643 | 1 |
| 5 | chunk | chunk:0415 | 0.0000 | 1.2643 | 1 |

## Book: The Odyssey

### Model: `all-mpnet-base-v2`
- Build: 11.4s, 5033 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 71ms
- mean_score=0.0000  mean_dist=1.1378  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1372 | 0.0000 | 1.1378 | 0 |
| 2 | chunk | chunk:1374 | 0.0000 | 1.1378 | 1 |
| 3 | chunk | chunk:1373 | 0.0000 | 1.1378 | 1 |
| 4 | chunk | chunk:1388 | 0.0000 | 1.1378 | 1 |
| 5 | chunk | chunk:1391 | 0.0000 | 1.1378 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 38ms
- mean_score=0.0000  mean_dist=1.2146  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | anger | 0.0000 | 1.1594 | 0 |
| 2 | chunk | chunk:0114 | 0.0000 | 1.1594 | 1 |
| 3 | chunk | chunk:0284 | 0.0000 | 1.1594 | 1 |
| 4 | chunk | chunk:1395 | 0.0000 | 1.2973 | 0 |
| 5 | entity | You | 0.0000 | 1.2973 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 33ms
- mean_score=0.0000  mean_dist=1.1716  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | married | 0.0000 | 1.1488 | 0 |
| 2 | chunk | chunk:1563 | 0.0000 | 1.1488 | 1 |
| 3 | topic | topic:married_bk | 0.0000 | 1.1848 | 0 |
| 4 | keyword | suitors | 0.0000 | 1.1879 | 0 |
| 5 | chunk | chunk:1086 | 0.0000 | 1.1879 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 33ms
- mean_score=0.0000  mean_dist=1.0946  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0005 | 0.0000 | 1.0946 | 0 |
| 2 | entity | Ithaca | 0.0000 | 1.0946 | 1 |
| 3 | keyword | his | 0.0000 | 1.0946 | 1 |
| 4 | entity | Greek | 0.0000 | 1.0946 | 1 |
| 5 | topic | topic:his_home | 0.0000 | 1.0946 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 32ms
- mean_score=0.0000  mean_dist=1.3395  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:his_himself | 0.0000 | 1.2984 | 0 |
| 2 | topic | topic:own_shall | 0.0000 | 1.3391 | 0 |
| 3 | chunk | chunk:0085 | 0.0000 | 1.3391 | 1 |
| 4 | keyword | liberty | 0.0000 | 1.3604 | 0 |
| 5 | chunk | chunk:0009 | 0.0000 | 1.3604 | 1 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 6.0s, 5033 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 58ms
- mean_score=0.4025  mean_dist=0.5975  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:they_murder | 0.4093 | 0.5907 | 0 |
| 2 | chunk | chunk:1291 | 0.4093 | 0.5907 | 1 |
| 3 | topic | topic:fair_therefore | 0.4040 | 0.5960 | 0 |
| 4 | chunk | chunk:0166 | 0.4040 | 0.5960 | 1 |
| 5 | chunk | chunk:0722 | 0.3860 | 0.6140 | 0 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 51ms
- mean_score=0.3485  mean_dist=0.6515  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | anger | 0.3776 | 0.6224 | 0 |
| 2 | chunk | chunk:0284 | 0.3776 | 0.6224 | 1 |
| 3 | chunk | chunk:0114 | 0.3776 | 0.6224 | 1 |
| 4 | section | BOOK XXII THE KILLING OF THE SUITORS—THE MAIDS WHO | 0.3049 | 0.6951 | 0 |
| 5 | chunk | chunk:1394 | 0.3049 | 0.6951 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 40ms
- mean_score=0.3285  mean_dist=0.6715  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | married | 0.3865 | 0.6135 | 0 |
| 2 | chunk | chunk:1563 | 0.3865 | 0.6135 | 1 |
| 3 | topic | topic:married_bk | 0.3017 | 0.6983 | 0 |
| 4 | keyword | husband | 0.2840 | 0.7160 | 0 |
| 5 | chunk | chunk:1258 | 0.2840 | 0.7160 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 35ms
- mean_score=0.2843  mean_dist=0.7157  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1636 | 0.2843 | 0.7157 | 0 |
| 2 | chunk | chunk:1635 | 0.2843 | 0.7157 | 1 |
| 3 | chunk | chunk:1637 | 0.2843 | 0.7157 | 1 |
| 4 | chunk | chunk:1657 | 0.2843 | 0.7157 | 1 |
| 5 | section | FOOTNOTES: | 0.2843 | 0.7157 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 38ms
- mean_score=0.3200  mean_dist=0.6800  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | myself | 0.3298 | 0.6702 | 0 |
| 2 | chunk | chunk:0569 | 0.3298 | 0.6702 | 1 |
| 3 | chunk | chunk:0604 | 0.3298 | 0.6702 | 1 |
| 4 | chunk | chunk:1218 | 0.3298 | 0.6702 | 1 |
| 5 | keyword | himself | 0.2807 | 0.7193 | 0 |

### Model: `all-MiniLM-L6-v2`
- Build: 2.4s, 5033 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 42ms
- mean_score=0.0000  mean_dist=1.1548  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1372 | 0.0000 | 1.1548 | 0 |
| 2 | keyword | all | 0.0000 | 1.1548 | 1 |
| 3 | keyword | you | 0.0000 | 1.1548 | 1 |
| 4 | entity | We | 0.0000 | 1.1548 | 1 |
| 5 | entity | gold | 0.0000 | 1.1548 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 29ms
- mean_score=0.0000  mean_dist=1.2612  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1157 | 0.0000 | 1.2612 | 0 |
| 2 | chunk | chunk:1181 | 0.0000 | 1.2612 | 1 |
| 3 | chunk | chunk:1130 | 0.0000 | 1.2612 | 1 |
| 4 | chunk | chunk:1070 | 0.0000 | 1.2612 | 1 |
| 5 | chunk | chunk:1170 | 0.0000 | 1.2612 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 39ms
- mean_score=0.0000  mean_dist=1.2045  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | married | 0.0000 | 1.1072 | 0 |
| 2 | chunk | chunk:1563 | 0.0000 | 1.1072 | 1 |
| 3 | topic | topic:married_bk | 0.0000 | 1.2415 | 0 |
| 4 | keyword | husband | 0.0000 | 1.2834 | 0 |
| 5 | chunk | chunk:1258 | 0.0000 | 1.2834 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 30ms
- mean_score=0.0000  mean_dist=1.2242  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0735 | 0.0000 | 1.2242 | 0 |
| 2 | chunk | chunk:0683 | 0.0000 | 1.2242 | 1 |
| 3 | chunk | chunk:0691 | 0.0000 | 1.2242 | 1 |
| 4 | chunk | chunk:0692 | 0.0000 | 1.2242 | 1 |
| 5 | chunk | chunk:0716 | 0.0000 | 1.2242 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 46ms
- mean_score=0.0000  mean_dist=1.2838  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | myself | 0.0000 | 1.2643 | 0 |
| 2 | chunk | chunk:0604 | 0.0000 | 1.2643 | 1 |
| 3 | chunk | chunk:0569 | 0.0000 | 1.2643 | 1 |
| 4 | chunk | chunk:1218 | 0.0000 | 1.2643 | 1 |
| 5 | keyword | liberty | 0.0000 | 1.3616 | 0 |

## Book: Pride and Prejudice

### Model: `all-mpnet-base-v2`
- Build: 9.9s, 4743 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 73ms
- mean_score=0.0101  mean_dist=0.9899  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | moral | 0.0126 | 0.9874 | 0 |
| 2 | chunk | chunk:0050 | 0.0126 | 0.9874 | 1 |
| 3 | chunk | chunk:0925 | 0.0084 | 0.9916 | 0 |
| 4 | chunk | chunk:0926 | 0.0084 | 0.9916 | 1 |
| 5 | chunk | chunk:0411 | 0.0084 | 0.9916 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 43ms
- mean_score=0.0594  mean_dist=0.9682  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | spite | 0.1134 | 0.8866 | 0 |
| 2 | chunk | chunk:0379 | 0.1134 | 0.8866 | 1 |
| 3 | keyword | bitterness | 0.0352 | 0.9648 | 0 |
| 4 | chunk | chunk:1684 | 0.0352 | 0.9648 | 1 |
| 5 | entity | Hate | 0.0000 | 1.1380 | 0 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 38ms
- mean_score=0.0000  mean_dist=1.0520  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0161 | 0.0000 | 1.0520 | 0 |
| 2 | entity | Charlotte | 0.0000 | 1.0520 | 1 |
| 3 | entity | You | 0.0000 | 1.0520 | 1 |
| 4 | chunk | chunk:0656 | 0.0000 | 1.0520 | 1 |
| 5 | chunk | chunk:0621 | 0.0000 | 1.0520 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 33ms
- mean_score=0.0000  mean_dist=1.0282  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:defiance_bingley | 0.0000 | 1.0238 | 0 |
| 2 | chunk | chunk:0926 | 0.0000 | 1.0238 | 1 |
| 3 | chunk | chunk:1379 | 0.0000 | 1.0312 | 0 |
| 4 | chunk | chunk:1378 | 0.0000 | 1.0312 | 1 |
| 5 | entity | Lizzy | 0.0000 | 1.0312 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 33ms
- mean_score=0.0000  mean_dist=1.2481  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1686 | 0.0000 | 1.2481 | 0 |
| 2 | entity | You | 0.0000 | 1.2481 | 1 |
| 3 | topic | topic:not_philosophy | 0.0000 | 1.2481 | 1 |
| 4 | chunk | chunk:1685 | 0.0000 | 1.2481 | 1 |
| 5 | entity | Painful | 0.0000 | 1.2481 | 1 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 11.0s, 4743 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 167ms
- mean_score=0.4818  mean_dist=0.5182  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | moral | 0.4960 | 0.5040 | 0 |
| 2 | chunk | chunk:0050 | 0.4960 | 0.5040 | 1 |
| 3 | chunk | chunk:0491 | 0.4724 | 0.5276 | 0 |
| 4 | chunk | chunk:1687 | 0.4724 | 0.5276 | 1 |
| 5 | chunk | chunk:0818 | 0.4724 | 0.5276 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 104ms
- mean_score=0.3659  mean_dist=0.6341  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | anger | 0.3776 | 0.6224 | 0 |
| 2 | chunk | chunk:0625 | 0.3776 | 0.6224 | 1 |
| 3 | chunk | chunk:0952 | 0.3581 | 0.6419 | 0 |
| 4 | chunk | chunk:0600 | 0.3581 | 0.6419 | 1 |
| 5 | chunk | chunk:0650 | 0.3581 | 0.6419 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 123ms
- mean_score=0.4286  mean_dist=0.5714  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.4286 | 0.5714 | 0 |
| 2 | chunk | chunk:1399 | 0.4286 | 0.5714 | 1 |
| 3 | chunk | chunk:0528 | 0.4286 | 0.5714 | 1 |
| 4 | chunk | chunk:1290 | 0.4286 | 0.5714 | 1 |
| 5 | chunk | chunk:0871 | 0.4286 | 0.5714 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 103ms
- mean_score=0.2779  mean_dist=0.7221  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1371 | 0.2779 | 0.7221 | 0 |
| 2 | chunk | chunk:0374 | 0.2779 | 0.7221 | 1 |
| 3 | chunk | chunk:0432 | 0.2779 | 0.7221 | 1 |
| 4 | chunk | chunk:0434 | 0.2779 | 0.7221 | 1 |
| 5 | chunk | chunk:0452 | 0.2779 | 0.7221 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 122ms
- mean_score=0.3403  mean_dist=0.6597  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | personal | 0.3560 | 0.6440 | 0 |
| 2 | chunk | chunk:0004 | 0.3560 | 0.6440 | 1 |
| 3 | keyword | myself | 0.3298 | 0.6702 | 0 |
| 4 | chunk | chunk:0952 | 0.3298 | 0.6702 | 1 |
| 5 | chunk | chunk:0442 | 0.3298 | 0.6702 | 1 |

### Model: `all-MiniLM-L6-v2`
- Build: 2.8s, 4743 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 236ms
- mean_score=0.0000  mean_dist=1.0527  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | moral | 0.0000 | 1.0382 | 0 |
| 2 | chunk | chunk:0050 | 0.0000 | 1.0382 | 1 |
| 3 | chunk | chunk:0491 | 0.0000 | 1.0624 | 0 |
| 4 | chunk | chunk:1687 | 0.0000 | 1.0624 | 1 |
| 5 | chunk | chunk:0818 | 0.0000 | 1.0624 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 102ms
- mean_score=0.0857  mean_dist=0.9143  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0287 | 0.0857 | 0.9143 | 0 |
| 2 | chunk | chunk:0443 | 0.0857 | 0.9143 | 1 |
| 3 | chunk | chunk:1013 | 0.0857 | 0.9143 | 1 |
| 4 | chunk | chunk:1395 | 0.0857 | 0.9143 | 1 |
| 5 | chunk | chunk:0472 | 0.0857 | 0.9143 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 104ms
- mean_score=0.0249  mean_dist=0.9751  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0161 | 0.0249 | 0.9751 | 0 |
| 2 | chunk | chunk:0160 | 0.0249 | 0.9751 | 1 |
| 3 | chunk | chunk:0162 | 0.0249 | 0.9751 | 1 |
| 4 | chunk | chunk:0184 | 0.0249 | 0.9751 | 1 |
| 5 | chunk | chunk:0526 | 0.0249 | 0.9751 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 154ms
- mean_score=0.0000  mean_dist=1.2688  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0321 | 0.0000 | 1.2688 | 0 |
| 2 | chunk | chunk:0443 | 0.0000 | 1.2688 | 1 |
| 3 | chunk | chunk:0987 | 0.0000 | 1.2688 | 1 |
| 4 | chunk | chunk:1395 | 0.0000 | 1.2688 | 1 |
| 5 | chunk | chunk:1313 | 0.0000 | 1.2688 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 104ms
- mean_score=0.0000  mean_dist=1.0245  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0870 | 0.0000 | 1.0245 | 0 |
| 2 | chunk | chunk:0869 | 0.0000 | 1.0245 | 1 |
| 3 | chunk | chunk:0871 | 0.0000 | 1.0245 | 1 |
| 4 | section | CHAPTER XXXIII. | 0.0000 | 1.0245 | 1 |
| 5 | entity | Now | 0.0000 | 1.0245 | 1 |

## Book: Les Miserables

### Model: `all-mpnet-base-v2`
- Build: 74.9s, 22501 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 368ms
- mean_score=0.1230  mean_dist=0.8770  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:6428 | 0.1230 | 0.8770 | 0 |
| 2 | chunk | chunk:6429 | 0.1230 | 0.8770 | 1 |
| 3 | chunk | chunk:6456 | 0.1230 | 0.8770 | 1 |
| 4 | topic | topic:his_without | 0.1230 | 0.8770 | 1 |
| 5 | keyword | his | 0.1230 | 0.8770 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 187ms
- mean_score=0.1385  mean_dist=0.8615  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.1552 | 0.8448 | 0 |
| 2 | chunk | chunk:0261 | 0.1552 | 0.8448 | 1 |
| 3 | chunk | chunk:5209 | 0.1552 | 0.8448 | 1 |
| 4 | keyword | spite | 0.1134 | 0.8866 | 0 |
| 5 | chunk | chunk:2738 | 0.1134 | 0.8866 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 152ms
- mean_score=0.0000  mean_dist=1.0566  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.0000 | 1.0566 | 0 |
| 2 | chunk | chunk:7055 | 0.0000 | 1.0566 | 1 |
| 3 | chunk | chunk:7010 | 0.0000 | 1.0566 | 1 |
| 4 | chunk | chunk:7011 | 0.0000 | 1.0566 | 1 |
| 5 | chunk | chunk:5400 | 0.0000 | 1.0566 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 128ms
- mean_score=0.0325  mean_dist=0.9873  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | heroism | 0.0812 | 0.9188 | 0 |
| 2 | chunk | chunk:6502 | 0.0812 | 0.9188 | 1 |
| 3 | topic | topic:man_conqueror | 0.0000 | 1.0323 | 0 |
| 4 | chunk | chunk:1879 | 0.0000 | 1.0323 | 1 |
| 5 | chunk | chunk:3569 | 0.0000 | 1.0342 | 0 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 120ms
- mean_score=0.0069  mean_dist=1.0712  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:identity_established | 0.0347 | 0.9653 | 0 |
| 2 | keyword | identity | 0.0000 | 1.0382 | 0 |
| 3 | chunk | chunk:1398 | 0.0000 | 1.0382 | 1 |
| 4 | topic | topic:liberty_sense | 0.0000 | 1.1572 | 0 |
| 5 | chunk | chunk:5214 | 0.0000 | 1.1572 | 1 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 148.7s, 22501 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 462ms
- mean_score=0.5034  mean_dist=0.4966  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | justice | 0.5034 | 0.4966 | 0 |
| 2 | chunk | chunk:0224 | 0.5034 | 0.4966 | 1 |
| 3 | chunk | chunk:4576 | 0.5034 | 0.4966 | 1 |
| 4 | chunk | chunk:6111 | 0.5034 | 0.4966 | 1 |
| 5 | chunk | chunk:6895 | 0.5034 | 0.4966 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 129ms
- mean_score=0.4728  mean_dist=0.5272  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Revenge | 0.4891 | 0.5109 | 0 |
| 2 | chunk | chunk:4165 | 0.4891 | 0.5109 | 1 |
| 3 | keyword | hatred | 0.4620 | 0.5380 | 0 |
| 4 | chunk | chunk:0261 | 0.4620 | 0.5380 | 1 |
| 5 | chunk | chunk:0522 | 0.4620 | 0.5380 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 154ms
- mean_score=0.4286  mean_dist=0.5714  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.4286 | 0.5714 | 0 |
| 2 | chunk | chunk:7010 | 0.4286 | 0.5714 | 1 |
| 3 | chunk | chunk:7011 | 0.4286 | 0.5714 | 1 |
| 4 | chunk | chunk:7047 | 0.4286 | 0.5714 | 1 |
| 5 | chunk | chunk:7055 | 0.4286 | 0.5714 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 106ms
- mean_score=0.3274  mean_dist=0.6726  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | heroes | 0.3362 | 0.6638 | 0 |
| 2 | chunk | chunk:3569 | 0.3362 | 0.6638 | 1 |
| 3 | section | CHAPTER X—THE SYSTEM OF DENIALS | 0.3215 | 0.6785 | 0 |
| 4 | chunk | chunk:1494 | 0.3215 | 0.6785 | 1 |
| 5 | chunk | chunk:1489 | 0.3215 | 0.6785 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 124ms
- mean_score=0.4008  mean_dist=0.5992  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | ourselves | 0.4091 | 0.5909 | 0 |
| 2 | chunk | chunk:2761 | 0.4091 | 0.5909 | 1 |
| 3 | chunk | chunk:7322 | 0.4091 | 0.5909 | 1 |
| 4 | keyword | identity | 0.3884 | 0.6116 | 0 |
| 5 | chunk | chunk:1398 | 0.3884 | 0.6116 | 1 |

### Model: `all-MiniLM-L6-v2`
- Build: 75.2s, 22501 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 282ms
- mean_score=0.0391  mean_dist=0.9609  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:which_justice | 0.1633 | 0.8367 | 0 |
| 2 | chunk | chunk:5221 | 0.0080 | 0.9920 | 0 |
| 3 | entity | We | 0.0080 | 0.9920 | 1 |
| 4 | chunk | chunk:5223 | 0.0080 | 0.9920 | 1 |
| 5 | chunk | chunk:5235 | 0.0080 | 0.9920 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 103ms
- mean_score=0.0288  mean_dist=0.9712  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.0412 | 0.9588 | 0 |
| 2 | chunk | chunk:0261 | 0.0412 | 0.9588 | 1 |
| 3 | chunk | chunk:5209 | 0.0412 | 0.9588 | 1 |
| 4 | chunk | chunk:7277 | 0.0101 | 0.9899 | 0 |
| 5 | chunk | chunk:7278 | 0.0101 | 0.9899 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 153ms
- mean_score=0.0000  mean_dist=1.0249  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.0000 | 1.0249 | 0 |
| 2 | chunk | chunk:7010 | 0.0000 | 1.0249 | 1 |
| 3 | chunk | chunk:7047 | 0.0000 | 1.0249 | 1 |
| 4 | chunk | chunk:7055 | 0.0000 | 1.0249 | 1 |
| 5 | chunk | chunk:7011 | 0.0000 | 1.0249 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 136ms
- mean_score=0.0000  mean_dist=1.1062  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:3507 | 0.0000 | 1.1062 | 0 |
| 2 | entity | There | 0.0000 | 1.1062 | 1 |
| 3 | entity | Every | 0.0000 | 1.1062 | 1 |
| 4 | chunk | chunk:3508 | 0.0000 | 1.1062 | 1 |
| 5 | chunk | chunk:3513 | 0.0000 | 1.1062 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 132ms
- mean_score=0.0000  mean_dist=1.0902  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:6186 | 0.0000 | 1.0902 | 0 |
| 2 | entity | This | 0.0000 | 1.0902 | 1 |
| 3 | entity | Equality | 0.0000 | 1.0902 | 1 |
| 4 | chunk | chunk:6187 | 0.0000 | 1.0902 | 1 |
| 5 | chunk | chunk:6188 | 0.0000 | 1.0902 | 1 |

## Book: Crime and Punishment

### Model: `all-mpnet-base-v2`
- Build: 82.8s, 7390 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 148ms
- mean_score=0.2370  mean_dist=0.7630  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0366 | 0.2370 | 0.7630 | 0 |
| 2 | entity | Well | 0.2370 | 0.7630 | 1 |
| 3 | entity | You | 0.2370 | 0.7630 | 1 |
| 4 | keyword | you | 0.2370 | 0.7630 | 1 |
| 5 | chunk | chunk:0367 | 0.2370 | 0.7630 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 65ms
- mean_score=0.0905  mean_dist=0.9095  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.1552 | 0.8448 | 0 |
| 2 | keyword | spite | 0.1134 | 0.8866 | 0 |
| 3 | chunk | chunk:1911 | 0.1134 | 0.8866 | 1 |
| 4 | keyword | bitterness | 0.0352 | 0.9648 | 0 |
| 5 | chunk | chunk:1362 | 0.0352 | 0.9648 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 71ms
- mean_score=0.0631  mean_dist=0.9369  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marriage | 0.0631 | 0.9369 | 0 |
| 2 | chunk | chunk:1879 | 0.0631 | 0.9369 | 1 |
| 3 | chunk | chunk:1880 | 0.0631 | 0.9369 | 1 |
| 4 | chunk | chunk:1882 | 0.0631 | 0.9369 | 1 |
| 5 | chunk | chunk:2667 | 0.0631 | 0.9369 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 46ms
- mean_score=0.0588  mean_dist=0.9412  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:2090 | 0.0588 | 0.9412 | 0 |
| 2 | chunk | chunk:2089 | 0.0588 | 0.9412 | 1 |
| 3 | topic | topic:if_into | 0.0588 | 0.9412 | 1 |
| 4 | chunk | chunk:2091 | 0.0588 | 0.9412 | 1 |
| 5 | keyword | if | 0.0588 | 0.9412 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 45ms
- mean_score=0.0000  mean_dist=1.0682  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | independence | 0.0000 | 1.0579 | 0 |
| 2 | chunk | chunk:1333 | 0.0000 | 1.0579 | 1 |
| 3 | topic | topic:freedom_him | 0.0000 | 1.0736 | 0 |
| 4 | entity | Freedom | 0.0000 | 1.0759 | 0 |
| 5 | chunk | chunk:1711 | 0.0000 | 1.0759 | 1 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 14.6s, 7390 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 255ms
- mean_score=0.5145  mean_dist=0.4855  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:her_justice | 0.5181 | 0.4819 | 0 |
| 2 | chunk | chunk:1517 | 0.5136 | 0.4864 | 0 |
| 3 | chunk | chunk:1197 | 0.5136 | 0.4864 | 1 |
| 4 | chunk | chunk:0208 | 0.5136 | 0.4864 | 1 |
| 5 | chunk | chunk:0210 | 0.5136 | 0.4864 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 65ms
- mean_score=0.4500  mean_dist=0.5500  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.4620 | 0.5380 | 0 |
| 2 | chunk | chunk:1667 | 0.4620 | 0.5380 | 1 |
| 3 | chunk | chunk:1959 | 0.4420 | 0.5580 | 0 |
| 4 | chunk | chunk:0415 | 0.4420 | 0.5580 | 1 |
| 5 | chunk | chunk:1893 | 0.4420 | 0.5580 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 79ms
- mean_score=0.4648  mean_dist=0.5352  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marriage | 0.4648 | 0.5352 | 0 |
| 2 | chunk | chunk:1880 | 0.4648 | 0.5352 | 1 |
| 3 | chunk | chunk:1882 | 0.4648 | 0.5352 | 1 |
| 4 | chunk | chunk:2667 | 0.4648 | 0.5352 | 1 |
| 5 | chunk | chunk:1883 | 0.4648 | 0.5352 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 67ms
- mean_score=0.3060  mean_dist=0.6940  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0707 | 0.3060 | 0.6940 | 0 |
| 2 | chunk | chunk:0583 | 0.3060 | 0.6940 | 1 |
| 3 | chunk | chunk:1147 | 0.3060 | 0.6940 | 1 |
| 4 | chunk | chunk:1197 | 0.3060 | 0.6940 | 1 |
| 5 | chunk | chunk:1537 | 0.3060 | 0.6940 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 73ms
- mean_score=0.4298  mean_dist=0.5702  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Freedom | 0.4321 | 0.5679 | 0 |
| 2 | chunk | chunk:1657 | 0.4321 | 0.5679 | 1 |
| 3 | chunk | chunk:1711 | 0.4321 | 0.5679 | 1 |
| 4 | keyword | freedom | 0.4263 | 0.5737 | 0 |
| 5 | chunk | chunk:0337 | 0.4263 | 0.5737 | 1 |

### Model: `all-MiniLM-L6-v2`
- Build: 12.2s, 7390 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 176ms
- mean_score=0.1430  mean_dist=0.8570  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0250 | 0.1430 | 0.8570 | 0 |
| 2 | chunk | chunk:0249 | 0.1430 | 0.8570 | 1 |
| 3 | chunk | chunk:0251 | 0.1430 | 0.8570 | 1 |
| 4 | section | CHAPTER IV | 0.1430 | 0.8570 | 1 |
| 5 | entity | Jesuitical | 0.1430 | 0.8570 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 61ms
- mean_score=0.0165  mean_dist=0.9868  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.0412 | 0.9588 | 0 |
| 2 | chunk | chunk:1667 | 0.0412 | 0.9588 | 1 |
| 3 | chunk | chunk:2512 | 0.0000 | 1.0054 | 0 |
| 4 | chunk | chunk:1087 | 0.0000 | 1.0054 | 1 |
| 5 | chunk | chunk:0014 | 0.0000 | 1.0054 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 60ms
- mean_score=0.0606  mean_dist=0.9551  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marriage | 0.0757 | 0.9243 | 0 |
| 2 | chunk | chunk:1879 | 0.0757 | 0.9243 | 1 |
| 3 | chunk | chunk:1882 | 0.0757 | 0.9243 | 1 |
| 4 | chunk | chunk:2667 | 0.0757 | 0.9243 | 1 |
| 5 | chunk | chunk:1883 | 0.0000 | 1.0782 | 0 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 58ms
- mean_score=0.0000  mean_dist=1.2680  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:1100 | 0.0000 | 1.2680 | 0 |
| 2 | chunk | chunk:0999 | 0.0000 | 1.2680 | 1 |
| 3 | chunk | chunk:1000 | 0.0000 | 1.2680 | 1 |
| 4 | chunk | chunk:1001 | 0.0000 | 1.2680 | 1 |
| 5 | chunk | chunk:1048 | 0.0000 | 1.2680 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 100ms
- mean_score=0.0000  mean_dist=1.0349  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | freedom | 0.0000 | 1.0321 | 0 |
| 2 | chunk | chunk:0337 | 0.0000 | 1.0321 | 1 |
| 3 | entity | Freedom | 0.0000 | 1.0368 | 0 |
| 4 | chunk | chunk:1657 | 0.0000 | 1.0368 | 1 |
| 5 | chunk | chunk:1711 | 0.0000 | 1.0368 | 1 |

## Book: Beyond Good and Evil

### Model: `all-mpnet-base-v2`
- Build: 26.2s, 4175 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 53ms
- mean_score=0.1882  mean_dist=0.8118  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0307 | 0.1882 | 0.8118 | 0 |
| 2 | keyword | one | 0.1882 | 0.8118 | 1 |
| 3 | chunk | chunk:0308 | 0.1882 | 0.8118 | 1 |
| 4 | chunk | chunk:0306 | 0.1882 | 0.8118 | 1 |
| 5 | topic | topic:one_ashamed | 0.1882 | 0.8118 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 20ms
- mean_score=0.1122  mean_dist=0.8878  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.1552 | 0.8448 | 0 |
| 2 | chunk | chunk:0121 | 0.1015 | 0.8985 | 0 |
| 3 | topic | topic:developed_emotions | 0.1015 | 0.8985 | 1 |
| 4 | chunk | chunk:0122 | 0.1015 | 0.8985 | 1 |
| 5 | keyword | developed | 0.1015 | 0.8985 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 20ms
- mean_score=0.0000  mean_dist=1.1563  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:love_who | 0.0000 | 1.1331 | 0 |
| 2 | chunk | chunk:0777 | 0.0000 | 1.1621 | 0 |
| 3 | keyword | all | 0.0000 | 1.1621 | 1 |
| 4 | topic | topic:one_all | 0.0000 | 1.1621 | 1 |
| 5 | entity | ALSO | 0.0000 | 1.1621 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 18ms
- mean_score=0.1688  mean_dist=0.8312  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0311 | 0.1688 | 0.8312 | 0 |
| 2 | entity | THERE | 0.1688 | 0.8312 | 1 |
| 3 | entity | Our | 0.1688 | 0.8312 | 1 |
| 4 | entity | Occasionally | 0.1688 | 0.8312 | 1 |
| 5 | topic | topic:criminal_deed | 0.1688 | 0.8312 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 17ms
- mean_score=0.0036  mean_dist=1.0084  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | freedom--the | 0.0091 | 0.9909 | 0 |
| 2 | chunk | chunk:0344 | 0.0091 | 0.9909 | 1 |
| 3 | topic | topic:desire_oneself | 0.0000 | 1.0046 | 0 |
| 4 | chunk | chunk:0107 | 0.0000 | 1.0046 | 1 |
| 5 | chunk | chunk:0098 | 0.0000 | 1.0510 | 0 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 7.6s, 4175 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 38ms
- mean_score=0.5358  mean_dist=0.4642  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:morality_conclusion | 0.5389 | 0.4611 | 0 |
| 2 | chunk | chunk:0408 | 0.5389 | 0.4611 | 1 |
| 3 | topic | topic:we_morality | 0.5369 | 0.4631 | 0 |
| 4 | topic | topic:moral_them | 0.5321 | 0.4679 | 0 |
| 5 | chunk | chunk:0176 | 0.5321 | 0.4679 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 21ms
- mean_score=0.4286  mean_dist=0.5714  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | hatred | 0.4620 | 0.5380 | 0 |
| 2 | chunk | chunk:0306 | 0.4202 | 0.5798 | 0 |
| 3 | entity | So | 0.4202 | 0.5798 | 1 |
| 4 | entity | red | 0.4202 | 0.5798 | 1 |
| 5 | topic | topic:him_one | 0.4202 | 0.5798 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 17ms
- mean_score=0.3901  mean_dist=0.6099  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | society | 0.4021 | 0.5979 | 0 |
| 2 | chunk | chunk:0407 | 0.4021 | 0.5979 | 1 |
| 3 | chunk | chunk:0706 | 0.4021 | 0.5979 | 1 |
| 4 | keyword | love | 0.3722 | 0.6278 | 0 |
| 5 | chunk | chunk:0519 | 0.3722 | 0.6278 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 19ms
- mean_score=0.2896  mean_dist=0.7104  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | fate | 0.3018 | 0.6982 | 0 |
| 2 | chunk | chunk:0309 | 0.3018 | 0.6982 | 1 |
| 3 | chunk | chunk:0506 | 0.2814 | 0.7186 | 0 |
| 4 | topic | topic:colours_different | 0.2814 | 0.7186 | 1 |
| 5 | entity | COLOURED | 0.2814 | 0.7186 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 17ms
- mean_score=0.4485  mean_dist=0.5515  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | freedom--the | 0.4732 | 0.5268 | 0 |
| 2 | chunk | chunk:0344 | 0.4732 | 0.5268 | 1 |
| 3 | entity | Freedom | 0.4321 | 0.5679 | 0 |
| 4 | chunk | chunk:0098 | 0.4321 | 0.5679 | 1 |
| 5 | chunk | chunk:0428 | 0.4321 | 0.5679 | 1 |

### Model: `all-MiniLM-L6-v2`
- Build: 2.3s, 4175 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 13ms
- mean_score=0.2616  mean_dist=0.7384  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0406 | 0.2616 | 0.7384 | 0 |
| 2 | chunk | chunk:0336 | 0.2616 | 0.7384 | 1 |
| 3 | chunk | chunk:0351 | 0.2616 | 0.7384 | 1 |
| 4 | chunk | chunk:0352 | 0.2616 | 0.7384 | 1 |
| 5 | chunk | chunk:0360 | 0.2616 | 0.7384 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 14ms
- mean_score=0.0671  mean_dist=0.9329  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0113 | 0.0671 | 0.9329 | 0 |
| 2 | chunk | chunk:0123 | 0.0671 | 0.9329 | 1 |
| 3 | chunk | chunk:0023 | 0.0671 | 0.9329 | 1 |
| 4 | chunk | chunk:0053 | 0.0671 | 0.9329 | 1 |
| 5 | chunk | chunk:0114 | 0.0671 | 0.9329 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 15ms
- mean_score=0.0000  mean_dist=1.0570  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0399 | 0.0000 | 1.0570 | 0 |
| 2 | topic | topic:already_community | 0.0000 | 1.0570 | 1 |
| 3 | keyword | even | 0.0000 | 1.0570 | 1 |
| 4 | chunk | chunk:0386 | 0.0000 | 1.0570 | 1 |
| 5 | entity | Granted | 0.0000 | 1.0570 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 11ms
- mean_score=0.0000  mean_dist=1.1249  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0797 | 0.0000 | 1.1249 | 0 |
| 2 | chunk | chunk:0796 | 0.0000 | 1.1249 | 1 |
| 3 | chunk | chunk:0798 | 0.0000 | 1.1249 | 1 |
| 4 | entity | ASSURED | 0.0000 | 1.1249 | 1 |
| 5 | entity | Galiani | 0.0000 | 1.1249 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 15ms
- mean_score=0.0000  mean_dist=1.0312  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | freedom--the | 0.0000 | 1.0276 | 0 |
| 2 | chunk | chunk:0344 | 0.0000 | 1.0276 | 1 |
| 3 | keyword | freedom | 0.0000 | 1.0321 | 0 |
| 4 | chunk | chunk:0497 | 0.0000 | 1.0321 | 1 |
| 5 | entity | Freedom | 0.0000 | 1.0368 | 0 |

## Book: Hamlet

### Model: `all-mpnet-base-v2`
- Build: 18.5s, 1905 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 39ms
- mean_score=0.0000  mean_dist=1.1054  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0245 | 0.0000 | 1.1054 | 0 |
| 2 | entity | There | 0.0000 | 1.1054 | 1 |
| 3 | chunk | chunk:0246 | 0.0000 | 1.1054 | 1 |
| 4 | entity | Even | 0.0000 | 1.1054 | 1 |
| 5 | entity | Yet | 0.0000 | 1.1054 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 19ms
- mean_score=0.0000  mean_dist=1.1079  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Revenge | 0.0000 | 1.0056 | 0 |
| 2 | chunk | chunk:0335 | 0.0000 | 1.0056 | 1 |
| 3 | chunk | chunk:0078 | 0.0000 | 1.0056 | 1 |
| 4 | chunk | chunk:0171 | 0.0000 | 1.2614 | 0 |
| 5 | chunk | chunk:0259 | 0.0000 | 1.2614 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 17ms
- mean_score=0.0000  mean_dist=1.1131  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.0000 | 1.0566 | 0 |
| 2 | chunk | chunk:0189 | 0.0000 | 1.0566 | 1 |
| 3 | topic | topic:fortune_love | 0.0000 | 1.1340 | 0 |
| 4 | entity | Marry | 0.0000 | 1.1591 | 0 |
| 5 | chunk | chunk:0097 | 0.0000 | 1.1591 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 18ms
- mean_score=0.0000  mean_dist=1.1514  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:fortinbras_horatio | 0.0000 | 1.1321 | 0 |
| 2 | chunk | chunk:0412 | 0.0000 | 1.1321 | 1 |
| 3 | topic | topic:reynaldo_polonius | 0.0000 | 1.1555 | 0 |
| 4 | chunk | chunk:0096 | 0.0000 | 1.1555 | 1 |
| 5 | topic | topic:hamlet_ambition | 0.0000 | 1.1817 | 0 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 17ms
- mean_score=0.0000  mean_dist=1.2780  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:itself_youth | 0.0000 | 1.2670 | 0 |
| 2 | chunk | chunk:0054 | 0.0000 | 1.2670 | 1 |
| 3 | entity | Thyself | 0.0000 | 1.2834 | 0 |
| 4 | chunk | chunk:0115 | 0.0000 | 1.2834 | 1 |
| 5 | entity | Rebellious | 0.0000 | 1.2891 | 0 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 5.2s, 1905 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 29ms
- mean_score=0.4700  mean_dist=0.5300  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0244 | 0.4700 | 0.5300 | 0 |
| 2 | section | SCENE III. A room in the Castle. | 0.4700 | 0.5300 | 1 |
| 3 | entity | Can | 0.4700 | 0.5300 | 1 |
| 4 | entity | Forgive | 0.4700 | 0.5300 | 1 |
| 5 | entity | May | 0.4700 | 0.5300 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 28ms
- mean_score=0.3724  mean_dist=0.6276  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Revenge | 0.4891 | 0.5109 | 0 |
| 2 | chunk | chunk:0078 | 0.4891 | 0.5109 | 1 |
| 3 | keyword | fear | 0.2999 | 0.7001 | 0 |
| 4 | chunk | chunk:0053 | 0.2999 | 0.7001 | 1 |
| 5 | entity | Dread | 0.2841 | 0.7159 | 0 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 27ms
- mean_score=0.3948  mean_dist=0.6052  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.4286 | 0.5714 | 0 |
| 2 | chunk | chunk:0189 | 0.4286 | 0.5714 | 1 |
| 3 | keyword | love | 0.3722 | 0.6278 | 0 |
| 4 | chunk | chunk:0121 | 0.3722 | 0.6278 | 1 |
| 5 | chunk | chunk:0214 | 0.3722 | 0.6278 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 28ms
- mean_score=0.2906  mean_dist=0.7094  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0167 | 0.2906 | 0.7094 | 0 |
| 2 | chunk | chunk:0001 | 0.2906 | 0.7094 | 1 |
| 3 | chunk | chunk:0011 | 0.2906 | 0.7094 | 1 |
| 4 | chunk | chunk:0023 | 0.2906 | 0.7094 | 1 |
| 5 | chunk | chunk:0025 | 0.2906 | 0.7094 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 29ms
- mean_score=0.3403  mean_dist=0.6597  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | ourselves | 0.4091 | 0.5909 | 0 |
| 2 | chunk | chunk:0218 | 0.4091 | 0.5909 | 1 |
| 3 | entity | Himself | 0.2983 | 0.7017 | 0 |
| 4 | chunk | chunk:0055 | 0.2983 | 0.7017 | 1 |
| 5 | entity | Being Nature | 0.2869 | 0.7131 | 0 |

### Model: `all-MiniLM-L6-v2`
- Build: 2.6s, 1905 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 34ms
- mean_score=0.0000  mean_dist=1.1021  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0245 | 0.0000 | 1.1021 | 0 |
| 2 | chunk | chunk:0246 | 0.0000 | 1.1021 | 1 |
| 3 | entity | Buys | 0.0000 | 1.1021 | 1 |
| 4 | entity | Even | 0.0000 | 1.1021 | 1 |
| 5 | entity | Offence | 0.0000 | 1.1021 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 28ms
- mean_score=0.0000  mean_dist=1.2270  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Revenge | 0.0000 | 1.1518 | 0 |
| 2 | chunk | chunk:0078 | 0.0000 | 1.1518 | 1 |
| 3 | chunk | chunk:0172 | 0.0000 | 1.2771 | 0 |
| 4 | chunk | chunk:0034 | 0.0000 | 1.2771 | 1 |
| 5 | chunk | chunk:0083 | 0.0000 | 1.2771 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 46ms
- mean_score=0.0000  mean_dist=1.0824  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marry | 0.0000 | 1.0249 | 0 |
| 2 | chunk | chunk:0189 | 0.0000 | 1.0249 | 1 |
| 3 | keyword | love | 0.0000 | 1.1207 | 0 |
| 4 | chunk | chunk:0121 | 0.0000 | 1.1207 | 1 |
| 5 | chunk | chunk:0214 | 0.0000 | 1.1207 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 25ms
- mean_score=0.0000  mean_dist=1.2522  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0293 | 0.0000 | 1.2522 | 0 |
| 2 | section | SCENE IV. A plain in Denmark. | 0.0000 | 1.2522 | 1 |
| 3 | entity | Bestial | 0.0000 | 1.2522 | 1 |
| 4 | entity | Now | 0.0000 | 1.2522 | 1 |
| 5 | entity | Sith | 0.0000 | 1.2522 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 27ms
- mean_score=0.0000  mean_dist=1.3216  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | ourselves | 0.0000 | 1.2914 | 0 |
| 2 | chunk | chunk:0218 | 0.0000 | 1.2914 | 1 |
| 3 | entity | Himself | 0.0000 | 1.3348 | 0 |
| 4 | chunk | chunk:0055 | 0.0000 | 1.3348 | 1 |
| 5 | keyword | ambition | 0.0000 | 1.3556 | 0 |

## Book: Don Quixote

### Model: `all-mpnet-base-v2`
- Build: 166.6s, 11500 rows, dim=768

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 397ms
- mean_score=0.0166  mean_dist=0.9834  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | justice | 0.0197 | 0.9803 | 0 |
| 2 | chunk | chunk:3221 | 0.0197 | 0.9803 | 1 |
| 3 | chunk | chunk:1637 | 0.0145 | 0.9855 | 0 |
| 4 | keyword | all | 0.0145 | 0.9855 | 1 |
| 5 | chunk | chunk:1644 | 0.0145 | 0.9855 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 84ms
- mean_score=0.0225  mean_dist=0.9894  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:disdain_jealousy | 0.0420 | 0.9580 | 0 |
| 2 | keyword | bitterness | 0.0352 | 0.9648 | 0 |
| 3 | chunk | chunk:0599 | 0.0352 | 0.9648 | 1 |
| 4 | keyword | disdain | 0.0000 | 1.0296 | 0 |
| 5 | chunk | chunk:0604 | 0.0000 | 1.0296 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 109ms
- mean_score=0.0323  mean_dist=0.9790  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marriage | 0.0631 | 0.9369 | 0 |
| 2 | chunk | chunk:0553 | 0.0631 | 0.9369 | 1 |
| 3 | keyword | marrying | 0.0177 | 0.9823 | 0 |
| 4 | chunk | chunk:2202 | 0.0177 | 0.9823 | 1 |
| 5 | keyword | marry | 0.0000 | 1.0566 | 0 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 61ms
- mean_score=0.0731  mean_dist=0.9269  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:2697 | 0.0731 | 0.9269 | 0 |
| 2 | topic | topic:over_soldier | 0.0731 | 0.9269 | 1 |
| 3 | entity | Terence | 0.0731 | 0.9269 | 1 |
| 4 | keyword | according | 0.0731 | 0.9269 | 1 |
| 5 | chunk | chunk:2696 | 0.0731 | 0.9269 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 59ms
- mean_score=0.0000  mean_dist=1.1465  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Freedom | 0.0000 | 1.0759 | 0 |
| 2 | keyword | freedom | 0.0000 | 1.1371 | 0 |
| 3 | chunk | chunk:3572 | 0.0000 | 1.1371 | 1 |
| 4 | topic | topic:himself_his | 0.0000 | 1.1912 | 0 |
| 5 | chunk | chunk:0307 | 0.0000 | 1.1912 | 1 |

### Model: `BAAI/bge-small-en-v1.5`
- Build: 73.4s, 11500 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 341ms
- mean_score=0.4888  mean_dist=0.5112  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | justice | 0.5034 | 0.4966 | 0 |
| 2 | chunk | chunk:3221 | 0.5034 | 0.4966 | 1 |
| 3 | topic | topic:came_justice | 0.5029 | 0.4971 | 0 |
| 4 | chunk | chunk:0607 | 0.4672 | 0.5328 | 0 |
| 5 | chunk | chunk:1052 | 0.4672 | 0.5328 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 95ms
- mean_score=0.3806  mean_dist=0.6194  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:disdain_jealousy | 0.3928 | 0.6072 | 0 |
| 2 | keyword | anger | 0.3776 | 0.6224 | 0 |
| 3 | chunk | chunk:0142 | 0.3776 | 0.6224 | 1 |
| 4 | chunk | chunk:2740 | 0.3776 | 0.6224 | 1 |
| 5 | chunk | chunk:3361 | 0.3776 | 0.6224 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 116ms
- mean_score=0.4431  mean_dist=0.5569  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marriage | 0.4648 | 0.5352 | 0 |
| 2 | chunk | chunk:0553 | 0.4648 | 0.5352 | 1 |
| 3 | keyword | marry | 0.4286 | 0.5714 | 0 |
| 4 | chunk | chunk:0555 | 0.4286 | 0.5714 | 1 |
| 5 | chunk | chunk:1176 | 0.4286 | 0.5714 | 1 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 93ms
- mean_score=0.2758  mean_dist=0.7242  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | knights-errant | 0.2885 | 0.7115 | 0 |
| 2 | chunk | chunk:1893 | 0.2885 | 0.7115 | 1 |
| 3 | entity | Heroic | 0.2723 | 0.7277 | 0 |
| 4 | chunk | chunk:3843 | 0.2723 | 0.7277 | 1 |
| 5 | topic | topic:him_dishonour | 0.2572 | 0.7428 | 0 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 88ms
- mean_score=0.4206  mean_dist=0.5794  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | entity | Freedom | 0.4321 | 0.5679 | 0 |
| 2 | keyword | freedom | 0.4263 | 0.5737 | 0 |
| 3 | chunk | chunk:3572 | 0.4263 | 0.5737 | 1 |
| 4 | keyword | ourselves | 0.4091 | 0.5909 | 0 |
| 5 | chunk | chunk:3594 | 0.4091 | 0.5909 | 1 |

### Model: `all-MiniLM-L6-v2`
- Build: 14.4s, 11500 rows, dim=384

#### Query: *what does the text say about justice and moral responsibility*
- k=8, hop=1, 217ms
- mean_score=0.0058  mean_dist=1.0022  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:came_justice | 0.0233 | 0.9767 | 0 |
| 2 | keyword | justice | 0.0028 | 0.9972 | 0 |
| 3 | chunk | chunk:3221 | 0.0028 | 0.9972 | 1 |
| 4 | entity | Justice | 0.0000 | 1.0200 | 0 |
| 5 | chunk | chunk:3227 | 0.0000 | 1.0200 | 1 |

#### Query: *revenge obsession and the consequences of hatred*
- k=8, hop=1, 75ms
- mean_score=0.0052  mean_dist=1.0664  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | topic | topic:disdain_jealousy | 0.0262 | 0.9738 | 0 |
| 2 | keyword | disdain | 0.0000 | 1.0699 | 0 |
| 3 | chunk | chunk:2785 | 0.0000 | 1.0961 | 0 |
| 4 | chunk | chunk:2794 | 0.0000 | 1.0961 | 1 |
| 5 | chunk | chunk:2724 | 0.0000 | 1.0961 | 1 |

#### Query: *love across social class and marriage in society*
- k=8, hop=1, 108ms
- mean_score=0.0532  mean_dist=0.9517  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | marriage | 0.0757 | 0.9243 | 0 |
| 2 | chunk | chunk:0553 | 0.0757 | 0.9243 | 1 |
| 3 | keyword | marrying | 0.0574 | 0.9426 | 0 |
| 4 | chunk | chunk:2202 | 0.0574 | 0.9426 | 1 |
| 5 | keyword | marry | 0.0000 | 1.0249 | 0 |

#### Query: *hubris fate and the downfall of heroes*
- k=8, hop=1, 74ms
- mean_score=0.0000  mean_dist=1.0960  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | chunk | chunk:0803 | 0.0000 | 1.0960 | 0 |
| 2 | chunk | chunk:0795 | 0.0000 | 1.0960 | 1 |
| 3 | chunk | chunk:0804 | 0.0000 | 1.0960 | 1 |
| 4 | chunk | chunk:1849 | 0.0000 | 1.0960 | 1 |
| 5 | chunk | chunk:0387 | 0.0000 | 1.0960 | 1 |

#### Query: *personal identity freedom and self-determination*
- k=8, hop=1, 148ms
- mean_score=0.0000  mean_dist=1.1116  returned=15

| Rank | Kind | Name | Score | Dist | Hop |
|---:|---|---|---:|---:|---:|
| 1 | keyword | freedom | 0.0000 | 1.0321 | 0 |
| 2 | chunk | chunk:3572 | 0.0000 | 1.0321 | 1 |
| 3 | entity | Freedom | 0.0000 | 1.0368 | 0 |
| 4 | entity | Willingly | 0.0000 | 1.2284 | 0 |
| 5 | chunk | chunk:3216 | 0.0000 | 1.2284 | 1 |
